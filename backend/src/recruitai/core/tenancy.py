"""Tenant resolution (ARCHITECTURE.md §4.4, ADR 0008).

``OrgContext`` always comes from the token + the ``X-Org-Id`` header, never from anything in
the request body. First-login provisioning (a ``users`` row, a personal ``organizations`` row,
an ``owner`` ``memberships`` row) happens atomically in this same dependency, using
``INSERT ... ON CONFLICT (firebase_uid)``: Postgres holds a row lock on the conflicting key for
the duration of the transaction, so two concurrent first requests for the same brand-new user
serialize on that lock — one of them inserts and creates the org, the other sees the conflict,
takes no other action, and (once unblocked, after the first commits) can see and reuse the
org the first one created. Neither path can observe or leave partial state, because the user
row, the org row and the membership row are all inserted in one transaction with one commit.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import Boolean, Row, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from recruitai.core.auth import CurrentUser, get_current_user
from recruitai.core.db import get_db
from recruitai.core.errors import Forbidden, NotFound
from recruitai.core.ids import new_id
from recruitai.modules.identity.models import Membership, Organization, User

LAST_ACTIVE_MIN_INTERVAL_S = 3600


@dataclass(frozen=True)
class OrgContext:
    org_id: UUID
    user_id: UUID
    role: str


async def _provision_user(
    session: AsyncSession, current: CurrentUser
) -> tuple[UUID, bool]:
    """Upsert by ``firebase_uid``. Returns ``(user_id, inserted)`` — ``inserted`` is True only
    for the request that actually created the row (Postgres ``xmax = 0``), which is exactly
    the one request, among any number of concurrent first-time callers, responsible for also
    creating the personal org."""
    row: Row[UUID, bool] = (
        await session.execute(
            pg_insert(User)
            .values(id=new_id(), firebase_uid=current.firebase_uid, email=current.email)
            .on_conflict_do_update(
                index_elements=[User.firebase_uid], set_={"email": current.email}
            )
            .returning(
                User.id, literal_column("(xmax = 0)", type_=Boolean).label("inserted")
            )
        )
    ).one()
    return row.id, bool(row.inserted)


async def _create_personal_org(session: AsyncSession, user_id: UUID) -> UUID:
    org_id = new_id()
    await session.execute(
        pg_insert(Organization).values(id=org_id, name="Personal", kind="personal")
    )
    await session.execute(
        pg_insert(Membership).values(
            id=new_id(), org_id=org_id, user_id=user_id, role="owner"
        )
    )
    return org_id


async def _touch_last_active(session: AsyncSession, user_id: UUID) -> None:
    """At most one write per hour per user (P2-31's retention sweep reads this column)."""
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .where(
            (User.last_active_at.is_(None))
            | (
                User.last_active_at
                < func.now()
                - literal_column(f"interval '{LAST_ACTIVE_MIN_INTERVAL_S} seconds'")
            )
        )
        .values(last_active_at=func.now())
    )


async def _is_blocked(session: AsyncSession, user_id: UUID) -> bool:
    return (
        await session.execute(select(User.blocked_at).where(User.id == user_id))
    ).scalar_one() is not None


async def _personal_org_id(session: AsyncSession, user_id: UUID) -> UUID:
    org_id = (
        await session.execute(
            select(Organization.id)
            .join(Membership, Membership.org_id == Organization.id)
            .where(Membership.user_id == user_id, Organization.kind == "personal")
            .limit(1)
        )
    ).scalar_one()
    return org_id


async def _membership_role(
    session: AsyncSession, org_id: UUID, user_id: UUID
) -> str | None:
    return (
        await session.execute(
            select(Membership.role).where(
                Membership.org_id == org_id, Membership.user_id == user_id
            )
        )
    ).scalar_one_or_none()


async def get_org_context(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> OrgContext:
    user_id, inserted = await _provision_user(db, current_user)
    if not inserted and await _is_blocked(db, user_id):
        raise Forbidden("This account has been blocked.")

    role: str | None
    if inserted:
        # The one request (among any concurrent first-timers) that created the user row:
        # it alone creates the personal org, in the same transaction.
        org_id = await _create_personal_org(db, user_id)
        role = "owner"
    elif x_org_id is None:
        org_id = await _personal_org_id(db, user_id)
        role = "owner"
    else:
        try:
            org_id = UUID(x_org_id)
        except ValueError:
            # Same response as "not a member": a malformed id must not look different from
            # one that's merely someone else's (ARCHITECTURE §4.4: never reveal existence).
            raise NotFound("Organization not found.") from None
        role = await _membership_role(db, org_id, user_id)
        if role is None:
            raise NotFound("Organization not found.")

    await _touch_last_active(db, user_id)
    await db.commit()
    return OrgContext(org_id=org_id, user_id=user_id, role=role)


def require_role(
    *roles: str,
) -> Callable[[OrgContext], Coroutine[Any, Any, OrgContext]]:
    async def _dependency(
        ctx: Annotated[OrgContext, Depends(get_org_context)],
    ) -> OrgContext:
        if ctx.role not in roles:
            raise Forbidden("You do not have the required role for this action.")
        return ctx

    return _dependency
