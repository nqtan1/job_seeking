"""Tenant resolution (ARCHITECTURE.md §4.4, ADR 0008).

``OrgContext`` comes from the token + ``X-Org-Id``, never the body. First-login provisioning (user,
personal org, owner membership) is one transaction using ``INSERT ... ON CONFLICT (firebase_uid)``,
so concurrent first requests serialize on the row lock and share one org.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
from recruitai.core.language import Language
from recruitai.modules.identity.models import Membership, Organization, User

LAST_ACTIVE_MIN_INTERVAL_S = 3600


@dataclass(frozen=True)
class OrgContext:
    org_id: UUID
    user_id: UUID
    role: str
    language: Language = "en"


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
    """At most one write per hour per user (the retention sweep reads this column)."""
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


async def _member_org(
    session: AsyncSession, user_id: UUID, x_org_id: str
) -> tuple[UUID, str]:
    try:
        org_id = UUID(x_org_id)
    except ValueError:
        # Same response as "not a member": a malformed id must not look different from
        # one that's merely someone else's (ARCHITECTURE §4.4: never reveal existence).
        raise NotFound("Organization not found.") from None
    role = await _membership_role(session, org_id, user_id)
    if role is None:
        raise NotFound("Organization not found.")
    return org_id, role


_UserRow = Row[UUID, str, datetime | None, datetime | None, str, UUID]


async def _lookup(session: AsyncSession, firebase_uid: str) -> _UserRow | None:
    """The hot path's single read: the user, whether it is blocked, and its personal org."""
    personal = (
        select(Organization.id)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == User.id, Organization.kind == "personal")
        .limit(1)
        .scalar_subquery()
    )
    return (
        await session.execute(
            select(
                User.id,
                User.email,
                User.blocked_at,
                User.last_active_at,
                User.language,
                personal.label("personal_org_id"),
            ).where(User.firebase_uid == firebase_uid)
        )
    ).one_or_none()


def _needs_write(
    row: _UserRow,
    current: CurrentUser,
) -> bool:
    """Only when the e-mail changed or the hourly ``last_active_at`` is due: otherwise the
    request does not write at all (a write per request was the cost of every API call)."""
    return (
        row.email != current.email
        or row.last_active_at is None
        or row.last_active_at
        < datetime.now(UTC) - timedelta(seconds=LAST_ACTIVE_MIN_INTERVAL_S)
    )


async def get_org_context(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> OrgContext:
    role: str
    row = await _lookup(db, current_user.firebase_uid)
    if row is not None:
        # Hot path (every request after the first login): one SELECT, no write.
        if row.blocked_at is not None:
            raise Forbidden("This account has been blocked.")
        user_id = row.id
        if _needs_write(row, current_user):
            await db.execute(
                update(User).where(User.id == user_id).values(email=current_user.email)
            )
            await _touch_last_active(db, user_id)
        if x_org_id is None:
            org_id = row.personal_org_id or await _personal_org_id(db, user_id)
            role = "owner"
        else:
            org_id, role = await _member_org(db, user_id, x_org_id)
        await db.commit()
        return OrgContext(
            org_id=org_id,
            user_id=user_id,
            role=role,
            language=row.language,
        )

    user_id, inserted = await _provision_user(db, current_user)
    if not inserted and await _is_blocked(db, user_id):
        raise Forbidden("This account has been blocked.")

    if inserted:
        # The one request (among any concurrent first-timers) that created the user row:
        # it alone creates the personal org, in the same transaction.
        org_id = await _create_personal_org(db, user_id)
        role = "owner"
    elif x_org_id is None:
        org_id = await _personal_org_id(db, user_id)
        role = "owner"
    else:
        org_id, role = await _member_org(db, user_id, x_org_id)

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
