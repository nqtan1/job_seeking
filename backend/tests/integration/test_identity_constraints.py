"""P1-02: the identity constraints actually reject bad data (one test per rule)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.identity.models import Membership, Organization, User


def _user(uid: str = "fb-1") -> User:
    return User(firebase_uid=uid, email=f"{uid}@example.test")


async def _persist(session: AsyncSession, *objs):
    session.add_all(objs)
    await session.flush()


async def _rejects(session: AsyncSession, obj, match: str | None = None) -> None:
    with pytest.raises(IntegrityError, match=match):
        async with session.begin_nested():
            session.add(obj)


async def _count(session: AsyncSession, table: str) -> int:
    return (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()


async def test_ids_are_uuid7_and_created_at_is_set_by_the_database(
    db_session: AsyncSession,
):
    org, user = Organization(name="Ada", kind="personal"), _user()
    await _persist(db_session, org, user)

    assert org.id.version == 7 and user.id.version == 7
    assert abs(datetime.now(UTC) - org.created_at) < timedelta(minutes=1)


async def test_user_rules_unique_firebase_uid_required_fields_and_upsert_shape(
    db_session: AsyncSession,
):
    await _persist(db_session, _user("dup"))
    await _rejects(db_session, _user("dup"), "uq_users_firebase_uid")
    await _rejects(db_session, User(email="a@example.test"))  # no firebase_uid
    await _rejects(db_session, User(firebase_uid="x"))  # no email

    # P1-07 provisions with INSERT ... ON CONFLICT (firebase_uid): it must be possible.
    upsert = text(
        "INSERT INTO users (id, firebase_uid, email) VALUES (:id, 'same', 'a@example.test') "
        "ON CONFLICT (firebase_uid) DO UPDATE SET email = EXCLUDED.email RETURNING id"
    )
    first = (await db_session.execute(upsert, {"id": uuid.uuid4()})).scalar_one()
    second = (await db_session.execute(upsert, {"id": uuid.uuid4()})).scalar_one()
    assert first == second


async def test_organization_kind_and_required_fields(db_session: AsyncSession):
    for bad in ("", "Personal", "team", "PERSONAL"):
        await _rejects(
            db_session, Organization(name="x", kind=bad), "ck_organizations_kind"
        )
    await _rejects(db_session, Organization(name=None, kind="personal"))  # type: ignore[arg-type]
    await _rejects(db_session, Organization(name="x", kind=None))  # type: ignore[arg-type]


async def test_membership_uniqueness_role_and_references(db_session: AsyncSession):
    o1, o2 = (
        Organization(name="A", kind="personal"),
        Organization(name="B", kind="company"),
    )
    u1, u2 = _user("u1"), _user("u2")
    await _persist(db_session, o1, o2, u1, u2)
    # a user can be in two orgs and an org can have two users
    await _persist(
        db_session,
        Membership(org_id=o1.id, user_id=u1.id, role="owner"),
        Membership(org_id=o2.id, user_id=u1.id, role="member"),
        Membership(org_id=o2.id, user_id=u2.id, role="recruiter"),
    )
    assert await _count(db_session, "memberships") == 3

    await _rejects(
        db_session,
        Membership(org_id=o1.id, user_id=u1.id, role="member"),
        "uq_memberships_org_id_user_id",
    )
    for bad in ("", "admin", "Owner", "guest"):
        await _rejects(
            db_session,
            Membership(org_id=o1.id, user_id=u2.id, role=bad),
            "ck_memberships_role",
        )
    await _rejects(
        db_session,
        Membership(org_id=uuid.uuid4(), user_id=uuid.uuid4(), role="owner"),
        "fk_memberships",
    )


async def test_deleting_an_org_or_a_user_removes_their_memberships_only(
    db_session: AsyncSession,
):
    o1, o2, user = (
        Organization(name="A", kind="personal"),
        Organization(name="B", kind="company"),
        _user(),
    )
    await _persist(db_session, o1, o2, user)
    await _persist(
        db_session,
        Membership(org_id=o1.id, user_id=user.id, role="owner"),
        Membership(org_id=o2.id, user_id=user.id, role="member"),
    )
    o1_id, user_id = o1.id, user.id

    await db_session.execute(
        text("DELETE FROM organizations WHERE id = :i"), {"i": o1_id}
    )
    assert (
        await _count(db_session, "memberships"),
        await _count(db_session, "users"),
    ) == (1, 1)

    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    assert (
        await _count(db_session, "memberships"),
        await _count(db_session, "organizations"),
    ) == (0, 1)
