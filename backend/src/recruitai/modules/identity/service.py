"""Business logic for the identity module. No FastAPI imports (import-linter enforced)."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import overrides, usage
from recruitai.config import AGENTS, Settings
from recruitai.core.email import EmailSender
from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.tenancy import OrgContext
from recruitai.modules.applications import service as applications
from recruitai.modules.candidates import service as candidates
from recruitai.modules.identity.models import (
    AdminAction,
    Membership,
    Organization,
    User,
)
from recruitai.modules.jobs import service as jobs
from recruitai.modules.letters import service as letters

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeResult:
    user_id: UUID
    email: str
    display_name: str | None
    active_org_id: UUID
    has_profile: bool
    email_reminders: bool


async def get_me(db: AsyncSession, ctx: OrgContext) -> MeResult:
    user = (await db.execute(select(User).where(User.id == ctx.user_id))).scalar_one()
    return MeResult(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        active_org_id=ctx.org_id,
        has_profile=await candidates.has_profile(db, org_id=ctx.org_id),
        email_reminders=user.email_reminders,
    )


async def export_data(
    db: AsyncSession, *, org_id: UUID, user_id: UUID
) -> dict[str, Any]:
    """The account itself: who they are and the personal org. Firebase uid is left out (an
    internal identifier, not data the user supplied)."""
    from recruitai.modules.identity.models import Organization

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    return {
        "user": {
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat(),
        },
        "organization": {"name": org.name, "kind": org.kind},
    }


async def owned_org_ids(db: AsyncSession, *, user_id: UUID) -> list[UUID]:
    """Orgs this user owns *alone*: deleting the account deletes these. (An org that has other
    members, a future company org, outlives one member leaving.)"""
    owned = select(Membership.org_id).where(
        Membership.user_id == user_id, Membership.role == "owner"
    )
    rows = await db.execute(
        select(Membership.org_id)
        .where(Membership.org_id.in_(owned))
        .group_by(Membership.org_id)
        .having(func.count(Membership.id) == 1)
    )
    return list(rows.scalars())


async def delete_account_rows(
    db: AsyncSession, *, user_id: UUID, org_ids: list[UUID]
) -> None:
    """Hard-delete the user and everything of theirs, in the caller's transaction. Deleting an
    organization cascades (ON DELETE CASCADE) to every module's rows: documents, profile, jobs,
    fit analyses, letters and versions, applications and events, coach conversations and
    messages, ``ai_calls``, ``task_runs``. Queued/finished Procrastinate jobs for those orgs
    live outside our schema, so they are removed explicitly."""
    for org_id in org_ids:
        if await db.scalar(text("SELECT to_regclass('procrastinate_jobs')")):
            await db.execute(
                text("DELETE FROM procrastinate_jobs WHERE args->>'org_id' = :org"),
                {"org": str(org_id)},
            )
    if org_ids:
        await db.execute(delete(Organization).where(Organization.id.in_(org_ids)))
    await db.execute(delete(User).where(User.id == user_id))


@dataclass(frozen=True)
class InactiveUser:
    id: UUID
    firebase_uid: str
    email: str
    last_active: datetime
    warned_at: datetime | None


async def inactive_users(
    db: AsyncSession, *, idle_since: datetime, limit: int
) -> list[InactiveUser]:
    """Users whose last activity (sign-up time if they never have any) is at or before
    ``idle_since``, oldest first, at most ``limit`` (a sweep processes a bounded batch)."""
    active = func.coalesce(User.last_active_at, User.created_at)
    rows = await db.execute(
        select(User, active).where(active <= idle_since).order_by(active).limit(limit)
    )
    return [
        InactiveUser(u.id, u.firebase_uid, u.email, last_active, u.deletion_warned_at)
        for u, last_active in rows.all()
    ]


async def mark_warned(db: AsyncSession, *, user_id: UUID, at: datetime) -> None:
    await db.execute(
        update(User).where(User.id == user_id).values(deletion_warned_at=at)
    )


async def list_users(
    db: AsyncSession, *, q: str | None, limit: int, offset: int
) -> tuple[list[User], int]:
    """Platform-wide user list for admins (the one deliberately cross-tenant read)."""
    where = [User.email.ilike(f"%{q}%")] if q else []
    total = (
        await db.execute(select(func.count()).select_from(User).where(*where))
    ).scalar_one()
    rows = await db.execute(
        select(User)
        .where(*where)
        .order_by(User.created_at.desc(), User.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars()), total


async def platform_stats(db: AsyncSession) -> dict[str, Any]:
    """Counts for the admin dashboard. Aggregates only: nothing here reveals user content."""
    now = datetime.now(UTC)
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    users_row = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(User.created_at >= d7),
                func.count().filter(User.created_at >= d30),
                func.count().filter(User.last_active_at >= d7),
                func.count().filter(User.last_active_at >= d30),
            ).select_from(User)
        )
    ).one()
    by_day = (
        await db.execute(
            select(func.date(User.created_at), func.count())
            .where(User.created_at >= d30)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
    ).all()
    by_status = await applications.count_by_status(db)
    ai = await usage.usage_since(db, since=d30)
    return {
        "users": dict(
            zip(
                ("total", "new_7d", "new_30d", "active_7d", "active_30d"),
                map(int, users_row),
                strict=True,
            )
        ),
        "signups_by_day": [{"day": str(d), "count": int(n)} for d, n in by_day],
        "content": {
            "profiles": await candidates.count_profiles(db),
            "jobs": await jobs.count_jobs(db),
            "letters": await letters.count_letters(db),
            "applications": sum(by_status.values()),
        },
        "applications_by_status": by_status,
        "ai_last_30d": [
            {
                "feature": f,
                "calls": c,
                "errors": e,
                "input_tokens": i,
                "output_tokens": o,
            }
            for f, c, e, i, o in ai
        ],
    }


async def set_blocked(
    db: AsyncSession,
    *,
    admin_uid: str,
    admin_emails: list[str],
    target_id: UUID,
    blocked: bool,
) -> User:
    """Block or unblock a user and record who did it. An admin cannot block themselves or
    another admin (that would lock the platform out of its own manager)."""
    target = (
        await db.execute(select(User).where(User.id == target_id).with_for_update())
    ).scalar_one_or_none()
    if target is None:
        raise NotFound("User not found.")
    if target.firebase_uid == admin_uid:
        raise ValidationFailed("You cannot block your own account.")
    if target.email.lower() in {e.lower() for e in admin_emails}:
        raise ValidationFailed("Admin accounts cannot be blocked.")
    admin_id = (
        await db.execute(select(User.id).where(User.firebase_uid == admin_uid))
    ).scalar_one_or_none()
    target.blocked_at = datetime.now(UTC) if blocked else None
    db.add(
        AdminAction(
            admin_user_id=admin_id,
            target_user_id=target.id,
            action="block" if blocked else "unblock",
        )
    )
    await db.commit()
    return target


async def set_email_reminders(
    db: AsyncSession, *, user_id: UUID, enabled: bool
) -> None:
    await db.execute(
        update(User).where(User.id == user_id).values(email_reminders=enabled)
    )
    await db.commit()


def _line(r: applications.Reminder) -> str:
    if r.kind == "interview":
        when = (
            "tomorrow / demain"
            if r.days == 1
            else f"in {r.days} days / dans {r.days} jours"
        )
        return f"- Interview at {r.company} {when}"
    return f"- {r.company}: no reply after {r.days} days / sans réponse depuis {r.days} jours"


async def active_owner_ids(
    db: AsyncSession, *, org_ids: list[UUID], active_since: datetime
) -> dict[UUID, UUID]:
    """``{org id: owner user id}`` for orgs whose owner is not blocked and was active since
    ``active_since`` (automated work is not spent on dormant or blocked accounts)."""
    if not org_ids:
        return {}
    rows = await db.execute(
        select(Membership.org_id, User.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.org_id.in_(org_ids),
            Membership.role == "owner",
            User.blocked_at.is_(None),
            User.last_active_at >= active_since,
        )
    )
    return {org_id: user_id for org_id, user_id in rows.all()}


async def send_application_reminders(
    db: AsyncSession,
    sender: EmailSender,
    *,
    now: datetime,
    extra_lines: dict[UUID, list[str]] | None = None,
) -> int:
    """One digest email per user: follow-ups and interviews due today, plus ``extra_lines``
    (e.g. the radar's new matches, per org). Skips users who opted out or are blocked. A failed
    send is logged by type only and does not stop the rest."""
    lines_by_org: dict[UUID, list[str]] = {}
    for r in await applications.due_reminders(db, today=now.date()):
        lines_by_org.setdefault(r.org_id, []).append(_line(r))
    for org_id, lines in (extra_lines or {}).items():
        lines_by_org.setdefault(org_id, []).extend(lines)
    if not lines_by_org:
        return 0
    rows = await db.execute(
        select(Membership.org_id, User.email)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.org_id.in_(set(lines_by_org)),
            Membership.role == "owner",
            User.email_reminders.is_(True),
            User.blocked_at.is_(None),
        )
    )
    sent = 0
    for org_id, email in rows.all():
        lines = lines_by_org[org_id]
        try:
            await sender.send(
                email,
                "application_reminders",
                {"count": len(lines), "lines": "\n".join(lines)},
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001  (one bad address must not stop the others)
            logger.error("reminder failed", extra={"error_type": type(exc).__name__})
    return sent


async def ai_console(db: AsyncSession, settings: Settings) -> dict[str, Any]:
    """The admin's view of every AI feature: what runs it now (default or override) and how it
    has behaved for 30 days. No prompts and no user content."""
    since = datetime.now(UTC) - timedelta(days=30)
    stats = await usage.feature_stats(db, since=since)
    active = await overrides.load(db)
    features = []
    for feature in AGENTS:
        default = settings.agents[feature]
        current = active.get(feature, default)
        features.append(
            {
                "feature": feature,
                "provider": current.provider,
                "model": current.model,
                "default": f"{default.provider}/{default.model}",
                "overridden": feature in active,
                "calls": 0,
                "errors": 0,
                "avg_latency_ms": 0,
                "p95_latency_ms": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "prompt_version": None,
                **stats.get(feature, {}),
            }
        )
    changes = [
        {
            "feature": c.feature,
            "old_value": c.old_value,
            "new_value": c.new_value,
            "at": c.at,
        }
        for c in await overrides.recent_changes(db)
    ]
    return {
        "features": features,
        "allowed_models": overrides.allowed_models(settings),
        "changes": changes,
    }


async def admin_user_id(db: AsyncSession, firebase_uid: str) -> UUID | None:
    return (
        await db.execute(select(User.id).where(User.firebase_uid == firebase_uid))
    ).scalar_one_or_none()
