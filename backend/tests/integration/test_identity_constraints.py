"""P1-02: the identity constraints actually reject bad data (behaviour, not just shape)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.identity.models import Membership, Organization, User


def _user(uid: str = "fb-1") -> User:
    return User(firebase_uid=uid, email=f"{uid}@example.test")


async def _persisted(session: AsyncSession, *objs):
    session.add_all(objs)
    await session.flush()


async def test_ids_are_uuid7_and_created_at_is_set_by_the_database(
    db_session: AsyncSession,
):
    org, user = Organization(name="Ada", kind="personal"), _user()
    await _persisted(db_session, org, user)

    assert org.id.version == 7 and user.id.version == 7
    assert org.created_at.tzinfo is not None
    assert abs(datetime.now(UTC) - org.created_at) < timedelta(minutes=1)


async def test_firebase_uid_must_be_unique(db_session: AsyncSession):
    await _persisted(db_session, _user("dup"))

    with pytest.raises(IntegrityError, match="uq_users_firebase_uid"):
        async with db_session.begin_nested():
            db_session.add(_user("dup"))


async def test_membership_is_unique_per_org_and_user(db_session: AsyncSession):
    org, user = Organization(name="Ada", kind="personal"), _user()
    await _persisted(db_session, org, user)
    await _persisted(
        db_session, Membership(org_id=org.id, user_id=user.id, role="owner")
    )

    with pytest.raises(IntegrityError, match="uq_memberships_org_id_user_id"):
        async with db_session.begin_nested():
            db_session.add(Membership(org_id=org.id, user_id=user.id, role="member"))


async def test_one_user_can_belong_to_two_orgs_and_one_org_to_two_users(
    db_session: AsyncSession,
):
    o1, o2 = (
        Organization(name="A", kind="personal"),
        Organization(name="B", kind="company"),
    )
    u1, u2 = _user("u1"), _user("u2")
    await _persisted(db_session, o1, o2, u1, u2)

    await _persisted(
        db_session,
        Membership(org_id=o1.id, user_id=u1.id, role="owner"),
        Membership(org_id=o2.id, user_id=u1.id, role="member"),
        Membership(org_id=o2.id, user_id=u2.id, role="recruiter"),
    )

    count = (
        await db_session.execute(select(text("count(*)")).select_from(Membership))
    ).scalar()
    assert count == 3


async def test_membership_requires_existing_org_and_user(db_session: AsyncSession):
    with pytest.raises(IntegrityError, match="fk_memberships"):
        async with db_session.begin_nested():
            db_session.add(
                Membership(org_id=uuid.uuid4(), user_id=uuid.uuid4(), role="owner")
            )


@pytest.mark.parametrize("kind", ["", "Personal", "team", "PERSONAL"])
async def test_invalid_org_kind_is_rejected(db_session: AsyncSession, kind: str):
    with pytest.raises(IntegrityError, match="ck_organizations_kind"):
        async with db_session.begin_nested():
            db_session.add(Organization(name="x", kind=kind))


@pytest.mark.parametrize("role", ["", "admin", "Owner", "guest"])
async def test_invalid_membership_role_is_rejected(db_session: AsyncSession, role: str):
    org, user = Organization(name="Ada", kind="personal"), _user()
    await _persisted(db_session, org, user)

    with pytest.raises(IntegrityError, match="ck_memberships_role"):
        async with db_session.begin_nested():
            db_session.add(Membership(org_id=org.id, user_id=user.id, role=role))


@pytest.mark.parametrize("field", ["name", "kind"])
async def test_organization_requires_name_and_kind(
    db_session: AsyncSession, field: str
):
    values = {"name": "x", "kind": "personal"}
    values[field] = None  # type: ignore[assignment]

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(Organization(**values))


async def test_user_requires_firebase_uid_and_email(db_session: AsyncSession):
    for bad in (User(email="a@example.test"), User(firebase_uid="x")):
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(bad)


async def _membership_count(session: AsyncSession) -> int:
    return (
        await session.execute(text("SELECT count(*) FROM memberships"))
    ).scalar_one()


async def test_deleting_an_org_deletes_its_memberships_only(db_session: AsyncSession):
    o1, o2, user = (
        Organization(name="A", kind="personal"),
        Organization(name="B", kind="company"),
        _user(),
    )
    await _persisted(db_session, o1, o2, user)
    await _persisted(
        db_session,
        Membership(org_id=o1.id, user_id=user.id, role="owner"),
        Membership(org_id=o2.id, user_id=user.id, role="member"),
    )

    await db_session.execute(
        text("DELETE FROM organizations WHERE id = :i"), {"i": o1.id}
    )

    assert await _membership_count(db_session) == 1
    still_there = (
        await db_session.execute(text("SELECT count(*) FROM users"))
    ).scalar_one()
    assert still_there == 1  # the user survives


async def test_deleting_a_user_deletes_their_memberships_but_not_the_org(
    db_session: AsyncSession,
):
    org, user = Organization(name="A", kind="personal"), _user()
    await _persisted(db_session, org, user)
    await _persisted(
        db_session, Membership(org_id=org.id, user_id=user.id, role="owner")
    )

    await db_session.execute(text("DELETE FROM users WHERE id = :i"), {"i": user.id})

    assert await _membership_count(db_session) == 0
    assert (
        await db_session.execute(text("SELECT count(*) FROM organizations"))
    ).scalar_one() == 1


async def test_on_conflict_provisioning_shape_works(db_session: AsyncSession):
    """P1-07 will provision with INSERT ... ON CONFLICT (firebase_uid): make sure it is possible."""
    stmt = text(
        "INSERT INTO users (id, firebase_uid, email) VALUES (:id, 'same', 'a@example.test') "
        "ON CONFLICT (firebase_uid) DO UPDATE SET email = EXCLUDED.email RETURNING id"
    )
    first = (await db_session.execute(stmt, {"id": uuid.uuid4()})).scalar_one()
    second = (await db_session.execute(stmt, {"id": uuid.uuid4()})).scalar_one()

    assert first == second
