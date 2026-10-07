"""Daily reminder digest: due items only, one email per user, opt-out and blocked respected."""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.auth import CurrentUser
from recruitai.core.email import FakeEmailSender
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
    assert sender.sent[0].context["count"] == 2
