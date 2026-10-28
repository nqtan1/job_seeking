"""Daily reminder digest: due items only, one email per user, opt-out and blocked respected."""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.auth import CurrentUser
from recruitai.core.email import FakeEmailSender, render
from recruitai.core.tenancy import get_org_context
from recruitai.modules.applications import repository
from recruitai.modules.identity import service
from recruitai.modules.identity.models import User

NOW = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)


async def _user(db: AsyncSession, tag: str):
    current = CurrentUser(
        f"uid-rem-{tag}-{uuid4().hex[:6]}", f"{tag}-{uuid4().hex[:6]}@example.test"
    )
    return current, await get_org_context(current, db, x_org_id=None)


async def _application(db: AsyncSession, org_id, company: str, **fields):
    app = await repository.create(
        db,
        org_id=org_id,
        job_id=None,
        company_name=company,
        job_title=None,
        source="other",
        status=fields.pop("status", "applied"),
        applied_at=fields.pop("applied_at", None),
        notes=None,
    )
    if fields:
        await repository.update(db, app, fields)
    return app


async def test_one_digest_per_user_for_items_due_today_only(db_session: AsyncSession):
    ada, ada_ctx = await _user(db_session, "ada")
    _bob, bob_ctx = await _user(db_session, "bob")
    _cara, cara_ctx = await _user(db_session, "cara")
    await _application(
        db_session, ada_ctx.org_id, "Quiet Inc", applied_at=date(2026, 10, 3)
    )
    await _application(
        db_session, ada_ctx.org_id, "Long Silence", applied_at=date(2026, 9, 19)
    )
    await _application(
        db_session,
        ada_ctx.org_id,
        "Soon Ltd",
        status="interview",
        interview_at=datetime(2026, 10, 13, 12, 0, tzinfo=UTC),
    )
    await _application(
        db_session, ada_ctx.org_id, "Too Early", applied_at=date(2026, 10, 6)
    )
    await _application(
        db_session, bob_ctx.org_id, "Opted Out", applied_at=date(2026, 10, 3)
    )
    await db_session.execute(
        update(User).where(User.id == bob_ctx.user_id).values(email_reminders=False)
    )
    await _application(
        db_session, cara_ctx.org_id, "Blocked Co", applied_at=date(2026, 10, 3)
    )
    await db_session.execute(
        update(User).where(User.id == cara_ctx.user_id).values(blocked_at=NOW)
    )
    sender = FakeEmailSender()

    sent = await service.send_application_reminders(db_session, sender, now=NOW)

    assert sent == 1 and [m.to for m in sender.sent] == [ada.email]
    lines = sender.sent[0].context["lines"]
    assert "Quiet Inc" in lines and "Soon Ltd" in lines and "Too Early" not in lines
    assert "Long Silence" in lines  # 21 days: the second nudge
    assert sender.sent[0].context["count"] == 3


async def test_weekly_goal_line_only_on_monday_and_only_when_opted_in(
    db_session: AsyncSession,
):
    _ada, ada_ctx = await _user(db_session, "goal")
    await _application(
        db_session, ada_ctx.org_id, "Sent Co", applied_at=date(2026, 10, 8)
    )
    sender = FakeEmailSender()
    monday = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)

    # No goal set: nothing to say, even on a Monday.
    assert await service.send_application_reminders(db_session, sender, now=monday) == 0

    await service.set_preferences(
        db_session, user_id=ada_ctx.user_id, changes={"weekly_goal": 3}
    )
    assert await service.send_application_reminders(db_session, sender, now=NOW) == 0

    assert await service.send_application_reminders(db_session, sender, now=monday) == 1
    assert "1 of 3" in sender.sent[0].context["lines"]


async def test_language_is_a_preference_and_the_digest_follows_it(
    db_session: AsyncSession,
):
    _ada, ada_ctx = await _user(db_session, "lang")
    await service.set_preferences(
        db_session,
        user_id=ada_ctx.user_id,
        changes={"language": "vi", "weekly_goal": 3},
    )
    await service.set_preferences(
        db_session, user_id=ada_ctx.user_id, changes={"language": None}
    )  # null never clears it
    assert (await service.get_me(db_session, ada_ctx)).language == "vi"

    await _application(
        db_session, ada_ctx.org_id, "Sent Co", applied_at=date(2026, 10, 1)
    )
    monday = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
    sender = FakeEmailSender()
    assert await service.send_application_reminders(db_session, sender, now=monday) == 1
    assert "Mục tiêu tuần" in sender.sent[0].context["lines"]
    assert "Xin chào" in render("application_reminders", sender.sent[0].context)[1]
