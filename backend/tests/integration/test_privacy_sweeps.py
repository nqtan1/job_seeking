"""Retention sweeps (P2-31) on a fake clock: each touches only rows past its own threshold,
the inactivity warning always comes first, and a draft letter is never swept."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.usage import AiCall
from recruitai.core.email import FakeEmailSender
from recruitai.core.errors import UpstreamUnavailable
from recruitai.core.storage import LocalStorage, ObjectNotFound
from recruitai.modules.documents import service as documents
from recruitai.modules.documents.models import Document
from recruitai.modules.identity.models import Membership, Organization, User
from recruitai.modules.jobs.models import JobSearchCache
from recruitai.modules.letters.models import Letter
from recruitai.modules.privacy import service
from tests.fixtures.org_data import seed_org

NOW = datetime(2028, 6, 1, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


async def _clean_slate(db: AsyncSession) -> None:
    """The sweeps act on EVERY account in the database, so a test must not see accounts that
    other tests committed for real. Deleting them here is rolled back with the test."""
    await db.execute(delete(User))


async def _user(
    db: AsyncSession, tag: str, *, idle_days: float
) -> tuple[Organization, User]:
    """An account with a personal org it owns, last active ``idle_days`` before NOW."""
    await _clean_slate(db)
    org = Organization(name=tag, kind="personal")
    user = User(
        firebase_uid=f"fb-{tag}",
        email=f"{tag}@example.test",
        last_active_at=NOW - idle_days * DAY,
    )
    db.add_all([org, user])
    await db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    await db.flush()
    return org, user


async def _sweep(
    db, storage, email, now, deleted_uids: list[str] | None = None
) -> dict[str, int]:
    deleted_uids = deleted_uids if deleted_uids is not None else []

    def delete_identity_for(uid: str):
        async def delete() -> None:
            deleted_uids.append(uid)

        return delete

    return await service.sweep_inactive_accounts(
        db, storage, email, now=now, delete_identity_for=delete_identity_for
    )


async def test_cache_ai_calls_and_exports_only_lose_rows_past_their_threshold(
    db_session: AsyncSession, fake_storage: LocalStorage
):
    org, user = await _user(db_session, "a", idle_days=1)
    db_session.add_all(
        [
            JobSearchCache(
                key="expired", provider="p", payload={}, expires_at=NOW
            ),  # at the instant
            JobSearchCache(
                key="live",
                provider="p",
                payload={},
                expires_at=NOW + timedelta(seconds=1),
            ),
        ]
    )
    for name, age in (("old", 396), ("edge", 395), ("new", 30)):
        db_session.add(
            AiCall(org_id=org.id, user_id=user.id, feature=name, model="m", prompt_version="p@1",
                   latency_ms=1, status="ok", created_at=NOW - age * DAY)
        )  # fmt: skip
    old_export = await documents.store_generated(
        db_session,
        fake_storage,
        org_id=org.id,
        kind="export",
        data=b"PK-old",
        mime="application/zip",
    )
    new_export = await documents.store_generated(
        db_session,
        fake_storage,
        org_id=org.id,
        kind="export",
        data=b"PK-new",
        mime="application/zip",
    )
    for doc, age in (
        (old_export, timedelta(hours=25)),
        (new_export, timedelta(hours=23)),
    ):
        await db_session.execute(
            update(Document).where(Document.id == doc.id).values(created_at=NOW - age)
        )
    await db_session.commit()

    assert await service.sweep_job_search_cache(db_session, now=NOW) == 1
    assert await service.sweep_ai_calls(db_session, now=NOW) == 1
    assert await service.sweep_exports(db_session, fake_storage, now=NOW) == 1

    assert [
        c.key for c in (await db_session.execute(select(JobSearchCache))).scalars()
    ] == ["live"]
    kept = (
        (await db_session.execute(select(AiCall.feature).order_by(AiCall.feature)))
        .scalars()
        .all()
    )
    assert kept == ["edge", "new"]  # exactly 13 months old is still kept
    assert [
        d.id
        for d in (
            await db_session.execute(select(Document).where(Document.kind == "export"))
        ).scalars()
    ] == [new_export.id]
    with __import__("pytest").raises(ObjectNotFound):
        await fake_storage.get(old_export.storage_key)  # the object went with the row
    assert await fake_storage.get(new_export.storage_key) == b"PK-new"


async def test_warnings_come_first_deletion_waits_a_week_after_the_last_one(
    db_session: AsyncSession, fake_storage: LocalStorage
):
    org, user = await _user(db_session, "a", idle_days=0)
    last_active = NOW - 701 * DAY
    await db_session.execute(
        update(User).where(User.id == user.id).values(last_active_at=last_active)
    )
    await db_session.commit()
    email = FakeEmailSender()
    gone: list[str] = []

    # 701 days idle: the 30-day warning, once.
    assert await _sweep(db_session, fake_storage, email, NOW, gone) == {
        "warned": 1,
        "deleted": 0,
    }
    assert await _sweep(db_session, fake_storage, email, NOW, gone) == {
        "warned": 0,
        "deleted": 0,
    }
    assert [(m.to, m.template, m.context["days_left"]) for m in email.sent] == [
        ("a@example.test", "inactivity_warning", 29)
    ]

    # 724 days: the 7-day warning. 728 days (4 days after it): nothing yet, and not deleted.
    t_final = last_active + 724 * DAY
    assert (await _sweep(db_session, fake_storage, email, t_final, gone))["warned"] == 1
    # deletion is never sooner than 7 days after the final warning: day 731, not 730
    assert email.sent[-1].context["days_left"] == 7
    assert await _sweep(
        db_session, fake_storage, email, last_active + 728 * DAY, gone
    ) == {"warned": 0, "deleted": 0}
    assert await _sweep(
        db_session, fake_storage, email, last_active + 730 * DAY, gone
    ) == {"warned": 0, "deleted": 0}  # 6 days after the warning: still waiting

    # 731 days = 7 days after the final warning, and past 24 months: now it is deleted.
    assert await _sweep(
        db_session, fake_storage, email, last_active + 731 * DAY, gone
    ) == {"warned": 0, "deleted": 1}
    assert gone == ["fb-a"] and len(email.sent) == 2  # no email after deletion
    assert await db_session.scalar(select(User).where(User.id == user.id)) is None
    assert (
        await db_session.scalar(select(Organization).where(Organization.id == org.id))
        is None
    )


async def test_a_long_idle_account_is_warned_before_it_is_ever_deleted(
    db_session: AsyncSession, fake_storage: LocalStorage
):
    await _user(
        db_session, "a", idle_days=800
    )  # far past 24 months and never warned (sweep was off)
    email, gone = FakeEmailSender(), []

    first = await _sweep(db_session, fake_storage, email, NOW, gone)
    assert first == {"warned": 1, "deleted": 0} and gone == []  # warning, NOT deletion
    assert (
        email.sent[0].context["delete_on"] == (NOW + 7 * DAY).date().isoformat()
    )  # a week from now

    assert await _sweep(db_session, fake_storage, email, NOW + 3 * DAY, gone) == {
        "warned": 0,
        "deleted": 0,
    }
    assert await _sweep(db_session, fake_storage, email, NOW + 7 * DAY, gone) == {
        "warned": 0,
        "deleted": 1,
    }
    assert len(email.sent) == 1 and gone == ["fb-a"]


async def test_coming_back_cancels_the_warnings_and_a_failed_email_is_retried(
    db_session: AsyncSession, fake_storage: LocalStorage
):
    _, user = await _user(db_session, "a", idle_days=701)
    email, gone = FakeEmailSender(), []
    await _sweep(db_session, fake_storage, email, NOW, gone)  # warned at 701 days
    assert len(email.sent) == 1

    # the user signs in again just before the final warning would have been due
    await db_session.execute(
        update(User).where(User.id == user.id).values(last_active_at=NOW + 10 * DAY)
    )
    await db_session.commit()
    much_later = NOW + 10 * DAY + 760 * DAY  # idle for 760 days again
    assert (await _sweep(db_session, fake_storage, email, much_later, gone))[
        "deleted"
    ] == 0
    assert (
        len(email.sent) == 2 and gone == []
    )  # the old warning was stale: warned afresh

    class Failing(FakeEmailSender):
        async def send(self, to, template, context):
            raise UpstreamUnavailable("down", code="email_unavailable")

    await _user(db_session, "b", idle_days=701)
    broken = Failing()
    assert await _sweep(db_session, fake_storage, broken, NOW, gone) == {
        "warned": 0,
        "deleted": 0,
    }
    again = FakeEmailSender()
    assert (await _sweep(db_session, fake_storage, again, NOW, gone))[
        "warned"
    ] == 1  # retried, not lost
    assert [m.to for m in again.sent] == ["b@example.test"]


async def test_no_sweep_ever_touches_a_thirty_day_old_draft_letter_or_other_user_data(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    await _clean_slate(db_session)
    owner = await seed_org(db_session, "keep", llm=fake_llm, storage=fake_storage)
    await db_session.execute(
        update(User).where(User.id == owner.user.id).values(last_active_at=NOW - DAY)
    )
    await db_session.execute(
        update(Letter)
        .where(Letter.org_id == owner.org_id)
        .values(created_at=NOW - 30 * DAY, status="draft")
    )
    await db_session.commit()
    before = {
        "letters": len(
            (
                await db_session.execute(
                    select(Letter).where(Letter.org_id == owner.org_id)
                )
            )
            .scalars()
            .all()
        ),
        "docs": len(
            (
                await db_session.execute(
                    select(Document).where(Document.org_id == owner.org_id)
                )
            )
            .scalars()
            .all()
        ),
    }

    email = FakeEmailSender()
    await service.sweep_job_search_cache(db_session, now=NOW)
    await service.sweep_ai_calls(db_session, now=NOW)
    await service.sweep_exports(db_session, fake_storage, now=NOW)
    await _sweep(db_session, fake_storage, email, NOW)

    letters = (
        (await db_session.execute(select(Letter).where(Letter.org_id == owner.org_id)))
        .scalars()
        .all()
    )
    assert len(letters) == before["letters"] and letters[0].status == "draft"
    docs = (
        (
            await db_session.execute(
                select(Document).where(Document.org_id == owner.org_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(docs) == before["docs"] and email.sent == []
