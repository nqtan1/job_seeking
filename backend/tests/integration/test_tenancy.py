"""core/tenancy.py (P1-07): atomic OrgContext provisioning."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.core.auth import CurrentUser
from recruitai.core.errors import NotFound
from recruitai.core.tenancy import _provision_user, get_org_context
from recruitai.modules.identity.models import Membership, Organization, User
from tests.fixtures.db import purge_tenant


def _user(tag: str) -> CurrentUser:
    return CurrentUser(
        firebase_uid=f"uid-tenancy-{tag}", email=f"tenancy-{tag}@example.test"
    )


async def test_first_login_provisions_exactly_one_org_atomically(
    db_session: AsyncSession,
):
    current = _user(uuid4().hex[:8])

    ctx = await get_org_context(current, db_session, x_org_id=None)

    assert ctx.role == "owner"
    users = (
        (
            await db_session.execute(
                select(User).where(User.firebase_uid == current.firebase_uid)
            )
        )
        .scalars()
        .all()
    )
    assert len(users) == 1 and users[0].id == ctx.user_id
    org = (
        await db_session.execute(
            select(Organization).where(Organization.id == ctx.org_id)
        )
    ).scalar_one()
    assert org.kind == "personal"
    membership = (
        await db_session.execute(
            select(Membership).where(Membership.user_id == ctx.user_id)
        )
    ).scalar_one()
    assert membership.role == "owner" and membership.org_id == ctx.org_id


async def test_returning_user_without_x_org_id_gets_the_same_personal_org(
    db_session: AsyncSession,
):
    current = _user(uuid4().hex[:8])
    first = await get_org_context(current, db_session, x_org_id=None)

    second = await get_org_context(current, db_session, x_org_id=None)

    assert (second.org_id, second.user_id, second.role) == (
        first.org_id,
        first.user_id,
        first.role,
    )
    count = (
        await db_session.execute(
            select(User).where(User.firebase_uid == current.firebase_uid)
        )
    ).scalars()
    assert len(count.all()) == 1  # still exactly one user row, not two


async def test_non_member_gets_404_not_403(db_session: AsyncSession):
    owner_ctx = await get_org_context(_user(uuid4().hex[:8]), db_session, x_org_id=None)
    intruder = _user(uuid4().hex[:8])
    await get_org_context(
        intruder, db_session, x_org_id=None
    )  # provisions their own org

    with pytest.raises(NotFound):
        await get_org_context(intruder, db_session, x_org_id=str(owner_ctx.org_id))


async def test_malformed_x_org_id_is_404_like_a_missing_one(db_session: AsyncSession):
    current = _user(uuid4().hex[:8])
    await get_org_context(current, db_session, x_org_id=None)

    with pytest.raises(NotFound):
        await get_org_context(current, db_session, x_org_id="not-a-uuid")


async def test_last_active_at_does_not_rewrite_within_the_same_hour(
    db_session: AsyncSession,
):
    current = _user(uuid4().hex[:8])
    ctx = await get_org_context(current, db_session, x_org_id=None)
    first_seen = (
        await db_session.execute(
            select(User.last_active_at).where(User.id == ctx.user_id)
        )
    ).scalar_one()
    assert first_seen is not None

    await get_org_context(current, db_session, x_org_id=None)

    second_seen = (
        await db_session.execute(
            select(User.last_active_at).where(User.id == ctx.user_id)
        )
    ).scalar_one()
    assert second_seen == first_seen


async def test_failure_before_commit_leaves_no_user_or_org(db_engine: AsyncEngine):
    """Proves the atomicity claim directly: if anything raises between the user upsert and
    the commit, the whole transaction (including the already-executed user insert) is
    discarded — a user can never exist without an org, not even transiently on disk."""
    current = _user(uuid4().hex[:8])

    async with db_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            _, inserted = await _provision_user(session, current)
            assert inserted
            raise RuntimeError("simulated failure before org/membership insert")
        except RuntimeError:
            pass
        finally:
            await session.close()
            await outer.rollback()

    async with db_engine.connect() as verify:
        count = (
            await verify.execute(
                text("SELECT count(*) FROM users WHERE firebase_uid = :u"),
                {"u": current.firebase_uid},
            )
        ).scalar()
        assert count == 0


async def test_concurrent_first_requests_create_exactly_one_org(db_engine: AsyncEngine):
    """The real concurrency proof: two simultaneous first-time requests for the same
    firebase_uid, each on its own connection/transaction, must serialize on the
    UNIQUE(firebase_uid) conflict and leave exactly one user/org/membership triple."""
    current = _user(uuid4().hex[:8])

    async def _one_request():
        async with db_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                return await get_org_context(current, session, x_org_id=None)
            finally:
                await session.close()

    ctx_a, ctx_b = await asyncio.gather(_one_request(), _one_request())
    try:
        assert ctx_a.org_id == ctx_b.org_id
        assert ctx_a.user_id == ctx_b.user_id

        async with db_engine.connect() as verify:
            user_count = (
                await verify.execute(
                    text("SELECT count(*) FROM users WHERE firebase_uid = :u"),
                    {"u": current.firebase_uid},
                )
            ).scalar()
            org_count = (
                await verify.execute(
                    text(
                        "SELECT count(*) FROM organizations o "
                        "JOIN memberships m ON m.org_id = o.id WHERE m.user_id = :uid"
                    ),
                    {"uid": str(ctx_a.user_id)},
                )
            ).scalar()
            assert (user_count, org_count) == (1, 1)
    finally:  # this test commits for real: remove it, other tests count rows globally
        await purge_tenant(db_engine, org_id=ctx_a.org_id, user_id=ctx_a.user_id)
