"""The background runs: the daily run, retries of interrupted runs, the digest lines and the
inactivity pause (ADR 0021, 0024)."""

import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway
from recruitai.core.language import Language
from recruitai.modules.identity import service as identity
from recruitai.modules.jobs.providers.base import JobProvider
from recruitai.modules.radar import repository
from recruitai.modules.radar.consent import consented_orgs
from recruitai.modules.radar.models import RadarRun, RadarSearch
from recruitai.modules.radar.runs import is_interrupted, run_search

logger = logging.getLogger(__name__)

IDLE_PAUSE_AFTER = timedelta(
    days=60
)  # no automatic runs for accounts idle this long (ADR 0024)
MAX_RUNS_PER_DAY = (
    500  # ponytail: one worker, runs one after another; shard when users grow
)
RETRY_AFTER = timedelta(minutes=20)  # automatic retry waits this long after the failure
MAX_AUTO_RETRIES = 3  # automatic retries per search per day
Notify = Callable[
    [UUID, str, dict[str, Any]], Awaitable[None]
]  # (user id, template, context)


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=UTC)


async def due_searches(
    db: AsyncSession, *, now: datetime, policy_version: str
) -> list[tuple[UUID, UUID, UUID]]:
    """``(search id, org id, owner user id)`` for enabled searches that have not run today, of
    owners who are neither blocked nor idle for 30 days."""
    searches = await repository.due_searches(
        db, ran_before=_day_start(now), limit=MAX_RUNS_PER_DAY
    )
    return await _runnable_targets(db, searches, now=now, policy_version=policy_version)


async def _runnable_targets(
    db: AsyncSession,
    searches: list[RadarSearch],
    *,
    now: datetime,
    policy_version: str,
) -> list[tuple[UUID, UUID, UUID]]:
    """The one gate for background runs: enabled, not held, consent current, owner active."""
    org_ids = list({s.org_id for s in searches})
    owners = await identity.active_owner_ids(
        db, org_ids=org_ids, active_since=now - IDLE_PAUSE_AFTER
    )
    consented = await consented_orgs(db, org_ids=org_ids, policy_version=policy_version)
    return [
        (s.id, s.org_id, owners[s.org_id])
        for s in searches
        if s.enabled
        and s.paused_reason is None
        and s.org_id in owners
        and s.org_id in consented
    ]


async def _run_each(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    llm_for: Callable[[AsyncSession, UUID, UUID], Awaitable[LLMGateway]],
    provider: JobProvider,
    targets: list[tuple[UUID, UUID, UUID]],
    *,
    quota: int,
    now: datetime,
    policy_version: str,
    notify: Notify | None = None,
    failures_before_pause: int,
) -> int:
    """Run each ``(search id, org id, owner user id)`` in its own session. Returns how many started.
    Consent is re-checked before each run."""
    started = 0
    for search_id, org_id, user_id in targets:
        async with session_factory() as session:
            current = await repository.searches_by_ids(session, search_ids=[search_id])
            if not await _runnable_targets(
                session, current, now=now, policy_version=policy_version
            ):
                continue
            try:
                run = await run_search(
                    session,
                    await llm_for(session, org_id, user_id),
                    provider,
                    org_id=org_id,
                    user_id=user_id,
                    search_id=search_id,
                    quota=quota,
                    now=now,
                )
                if run is not None:
                    await _record_outcome(
                        session,
                        current[0],
                        run,
                        user_id=user_id,
                        now=now,
                        notify=notify,
                        limit=failures_before_pause,
                    )
            except Exception as exc:  # noqa: BLE001  (e.g. the search was deleted meanwhile)
                logger.error(
                    "radar background run failed",
                    extra={"error_type": type(exc).__name__},
                )
                continue
            started += run is not None
    return started


async def _record_outcome(
    db: AsyncSession,
    search: RadarSearch,
    run: RadarRun,
    *,
    user_id: UUID,
    now: datetime,
    notify: Notify | None,
    limit: int,
) -> None:
    """A day that ended in error counts as a failure; ``limit`` in a row hold the radar and tell
    the user. A clean day resets the count (a partial run is neither)."""
    if run.status == "ok":
        search.consecutive_failures = 0
    elif run.status == "error":
        search.consecutive_failures += 1
        if search.consecutive_failures >= limit and search.paused_reason is None:
            search.paused_reason, search.paused_at = "failures", now
            if notify:
                await notify(user_id, "radar_paused_failures", {"name": search.name})
    await db.commit()


async def run_due_searches(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    llm_for: Callable[[AsyncSession, UUID, UUID], Awaitable[LLMGateway]],
    provider: JobProvider,
    *,
    quota: int,
    policy_version: str,
    now: datetime | None = None,
    notify: Notify | None = None,
    failures_before_pause: int,
) -> int:
    """The daily run: every due search once."""
    now = now or datetime.now(UTC)
    async with session_factory() as session:
        due = await due_searches(session, now=now, policy_version=policy_version)
    return await _run_each(
        session_factory,
        llm_for,
        provider,
        due,
        quota=quota,
        now=now,
        policy_version=policy_version,
        notify=notify,
        failures_before_pause=failures_before_pause,
    )


async def interrupted_searches(
    db: AsyncSession, *, now: datetime, policy_version: str
) -> list[tuple[UUID, UUID, UUID]]:
    """Daily searches whose latest run today was interrupted a while ago and have retries left.
    Same owner rules as the daily run (not blocked, active in the last 30 days)."""
    runs = await repository.runs_since(db, since=_day_start(now))
    by_search: dict[UUID, list[RadarRun]] = {}
    for r in runs:
        by_search.setdefault(r.search_id, []).append(r)
    wanted: list[UUID] = []
    for search_id, history in by_search.items():
        latest = history[-1]
        failures = sum(is_interrupted(r, now) for r in history)
        waited = now - (latest.finished_at or latest.started_at) >= RETRY_AFTER
        if is_interrupted(latest, now) and failures <= MAX_AUTO_RETRIES and waited:
            wanted.append(search_id)
    searches = await repository.searches_by_ids(db, search_ids=wanted)
    return await _runnable_targets(db, searches, now=now, policy_version=policy_version)


async def retry_interrupted_searches(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    llm_for: Callable[[AsyncSession, UUID, UUID], Awaitable[LLMGateway]],
    provider: JobProvider,
    *,
    quota: int,
    policy_version: str,
    now: datetime | None = None,
    notify: Notify | None = None,
    failures_before_pause: int,
) -> int:
    now = now or datetime.now(UTC)
    async with session_factory() as session:
        targets = await interrupted_searches(
            session, now=now, policy_version=policy_version
        )
    return await _run_each(
        session_factory,
        llm_for,
        provider,
        targets,
        quota=quota,
        now=now,
        policy_version=policy_version,
        notify=notify,
        failures_before_pause=failures_before_pause,
    )


_NEW_MATCHES: dict[str, Callable[[int], str]] = {
    "en": lambda n: f"- {n} new job{'s' if n > 1 else ''} match your radar",
    "fr": lambda n: (
        f"- {n} nouvelle{'s' if n > 1 else ''} offre{'s' if n > 1 else ''} pour votre radar"
    ),
    "vi": lambda n: f"- {n} việc làm mới phù hợp với radar của bạn",
}
_STOP_RADARS = {
    "en": "Stop radars",
    "fr": "Arrêter les radars",
    "vi": "Dừng các radar",
}


async def new_match_lines(
    db: AsyncSession,
    *,
    now: datetime,
    link_for: Callable[[UUID, UUID], str] | None = None,
) -> dict[UUID, Callable[[Language], list[str]]]:
    """Digest lines per org: how many new shortlisted jobs since yesterday, and the best three,
    then (if ``link_for`` is given) a no-login link that withdraws the radar consent."""
    since = now - timedelta(days=1)
    counts = await repository.new_counts_since(db, since=since)
    best = await repository.top_new_since(db, since=since, per_org=3)
    links: dict[UUID, str] = {}
    if link_for and counts:
        owners = await identity.active_owner_ids(
            db, org_ids=list(counts), active_since=datetime.min.replace(tzinfo=UTC)
        )
        links = {org: link_for(org, user) for org, user in owners.items()}

    def lines_for(org_id: UUID, n: int) -> Callable[[Language], list[str]]:
        def build(language: Language) -> list[str]:
            head = _NEW_MATCHES[language](n)
            top = [
                f"    · {r.title or '?'}, {r.company or '?'} ({round(r.score or 0)}%)"
                for r in best.get(org_id, [])
            ]
            link = (
                [f"  {_STOP_RADARS[language]}: {links[org_id]}"]
                if org_id in links
                else []
            )
            return [head, *top, *link]

        return build

    return {org_id: lines_for(org_id, n) for org_id, n in counts.items()}


async def pause_inactive(
    db: AsyncSession,
    notice: Callable[[str, dict[str, Any]], Awaitable[bool]],
    *,
    now: datetime,
    notice_days: int = 53,
    limit: int = 500,
) -> dict[str, int]:
    """Notice at ``notice_days`` idle (once per idle period), hold the radars at 60. Only users
    who still have a live radar are touched, so nobody is mailed about something already off."""
    out = {"noticed": 0, "paused": 0}
    idle = await identity.idle_owners(
        db, idle_since=now - timedelta(days=notice_days), limit=limit
    )
    live = await repository.orgs_with_live_searches(
        db, org_ids=[u.org_id for u in idle]
    )
    for u in idle:
        if u.org_id not in live:
            continue
        if now - u.last_active >= IDLE_PAUSE_AFTER:
            await repository.hold_org_searches(
                db, org_id=u.org_id, reason="inactive", now=now
            )
            await db.commit()
            out["paused"] += 1
        elif u.radar_notice_at is None or u.radar_notice_at < u.last_active:
            pause_on = (u.last_active + IDLE_PAUSE_AFTER).date().isoformat()
            if await notice(u.email, {"pause_on": pause_on, "language": u.language}):
                await identity.mark_radar_notice(db, user_id=u.user_id, at=now)
                await db.commit()
                out["noticed"] += 1
    return out
