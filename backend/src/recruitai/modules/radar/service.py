"""The job radar (ADR 0021): search → skip what is known → score → shortlist.

It *proposes*: nothing here contacts a company or applies anywhere. The only model calls are the
existing fit analyses, through the tenant-bound gateway, so the user's daily AI quota applies;
the radar also leaves ``QUOTA_RESERVE`` calls untouched for the user's own chat and letters.
Whether a job is shortlisted is decided by code (score ≥ the user's minimum), never by anything
the job text says. No FastAPI imports; the LLM and the provider arrive as arguments."""

import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import usage
from recruitai.ai.gateway import LLMGateway, QuotaExceeded
from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.tasks import enqueue
from recruitai.modules.applications import service as applications
from recruitai.modules.candidates import service as candidates
from recruitai.modules.identity import service as identity
from recruitai.modules.jobs import service as jobs
from recruitai.modules.jobs.providers.base import JobProvider
from recruitai.modules.jobs.schemas import UnifiedJobSearchResult
from recruitai.modules.matching import service as matching
from recruitai.modules.radar import repository
from recruitai.modules.radar.models import RadarResult, RadarRun, RadarSearch
from recruitai.modules.radar.schemas import (
    MAX_SEARCHES_PER_ORG,
    RadarSearchIn,
    RadarSearchUpdate,
)

logger = logging.getLogger(__name__)

DAILY_RUN_AT = time(6, 30)  # UTC; the cron in tasks.py
QUOTA_RESERVE = (
    15  # model calls per day left for the user's own chat, letters, fit checks
)
RUN_COOLDOWN = timedelta(minutes=5)  # between two "Run now" of the same search
RUN_TASK = "radar:run_search"  # registered by the worker (worker.py, namespace "radar")
STALE_RUN = timedelta(
    minutes=10
)  # an unfinished run older than this is treated as abandoned (the worker died)
INACTIVE_AFTER = timedelta(days=30)  # no automatic runs for accounts idle this long
MAX_RUNS_PER_DAY = (
    500  # ponytail: one worker, runs one after another; shard when users grow
)
# A run that stopped for a reason that is not the user's doing can simply be tried again.
RETRYABLE_STOPS = {
    "ai_unavailable",
    "provider_error",
    "internal_error",
    "worker_stopped",
}
RETRY_AFTER = timedelta(minutes=20)  # automatic retry waits this long after the failure
MAX_AUTO_RETRIES = 3  # automatic retries per search per day


async def get_search(db: AsyncSession, *, org_id: UUID, search_id: UUID) -> RadarSearch:
    search = await repository.get_search(db, org_id=org_id, search_id=search_id)
    if search is None:
        raise NotFound("Radar search not found.")
    return search


async def run_search(
    db: AsyncSession,
    llm: LLMGateway,
    provider: JobProvider,
    *,
    org_id: UUID,
    user_id: UUID,
    search_id: UUID,
    quota: int,
    now: datetime | None = None,
) -> RadarRun | None:
    """One run of one search. Returns None, writing nothing, if another run of this search is in
    progress. Otherwise it always leaves a ``radar_runs`` row that says what happened and why it
    stopped (done | limit | quota | no_profile | ai_unavailable | provider_error | internal_error)."""
    now = now or datetime.now(UTC)
    search = await get_search(db, org_id=org_id, search_id=search_id)
    # ponytail: check-then-insert, so two runs started in the same instant can both pass; the
    # seen ledger still dedupes the results, at worst some model calls are doubled.
    if await repository.other_run_in_progress(
        db, org_id=org_id, search_id=search.id, since=now - STALE_RUN
    ):
        return None
    run = await repository.start_run(db, org_id=org_id, search_id=search.id)
    await db.commit()
    counts = {"found": 0, "added": 0, "scored": 0, "shortlisted": 0}
    try:
        return await _execute(
            db, llm, provider, run, search, user_id, quota, now, counts
        )
    except Exception as exc:  # noqa: BLE001  (anything unexpected must still close the run)
        await db.rollback()
        logger.error("radar run failed", extra={"error_type": type(exc).__name__})
        return await _finish(
            db, run, search, now, "error", "internal_error", counts, "internal_error"
        )


MAX_ALTERNATIVES = 4  # keyword alternatives per radar: "IA Engineer, ML Engineer, ..."
MAX_OFFERS = 25


def keyword_alternatives(query: str | None) -> list[str | None]:
    """``"IA Engineer, ML Engineer"`` -> two searches. France Travail treats commas inside one
    search as AND, so alternatives (OR) are separate searches whose results are merged."""
    parts: list[str | None] = [p.strip() for p in (query or "").split(",") if p.strip()]
    return parts[:MAX_ALTERNATIVES] or [None]


async def _find_offers(
    db: AsyncSession, provider: JobProvider, search: RadarSearch, now: datetime
) -> list[UnifiedJobSearchResult]:
    """One search per keyword alternative (each cached for a day), merged without duplicates and
    interleaved, so every alternative is represented in the first offers looked at."""
    lists = []
    for query in keyword_alternatives(search.query):
        response = await jobs.search(
            db,
            provider,
            query=query,
            department=search.department,
            contract_type=search.contract_type,
            now=now,
        )
        lists.append(response.results)
    merged: list[UnifiedJobSearchResult] = []
    seen: set[str] = set()
    for rank in range(max((len(x) for x in lists), default=0)):
        for results in lists:
            if rank < len(results) and results[rank].id not in seen:
                seen.add(results[rank].id)
                merged.append(results[rank])
    return merged[:MAX_OFFERS]


async def _execute(
    db: AsyncSession,
    llm: LLMGateway,
    provider: JobProvider,
    run: RadarRun,
    search: RadarSearch,
    user_id: UUID,
    quota: int,
    now: datetime,
    counts: dict[str, int],
) -> RadarRun:
    org_id = search.org_id
    status, stop, error = "ok", "done", None

    if not await candidates.has_profile(db, org_id=org_id):
        return await _finish(db, run, search, now, "ok", "no_profile", counts)

    day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    left_limit = search.daily_limit - await repository.scored_since(
        db, org_id=org_id, search_id=search.id, since=day_start
    )
    left_quota = (
        quota - QUOTA_RESERVE - await usage.count_calls_today(db, user_id=user_id)
    )
    budget = min(left_limit, left_quota)
    if budget <= 0:
        reason = "limit" if left_limit <= 0 else "quota"
        return await _finish(db, run, search, now, "ok", reason, counts)

    try:
        offers = await _find_offers(db, provider, search, now)
    except ValidationFailed:  # a place or contract France Travail does not accept
        return await _finish(
            db, run, search, now, "error", "invalid_search", counts, "invalid_search"
        )
    except UpstreamUnavailable:
        return await _finish(
            db, run, search, now, "error", "provider_error", counts, "provider_error"
        )
    counts["found"] = len(offers)
    await repository.set_run_counts(run, counts)
    await db.commit()  # the page shows "found N" while the run goes on
    ids = [r.id for r in offers]
    skip = await repository.seen_external_ids(
        db, org_id=org_id, source=provider.name, external_ids=ids
    ) | await jobs.known_external_ids(
        db, org_id=org_id, source=provider.name, external_ids=ids
    )
    unseen = [r for r in offers if r.id not in skip]
    fresh = unseen[:budget]

    for result in fresh:
        try:
            posting = await jobs.save_new_search_result(
                db, provider, org_id=org_id, external_id=result.id
            )
        except NotFound:
            continue  # the offer was withdrawn since the search
        except UpstreamUnavailable:
            status, stop, error = "partial", "provider_error", "provider_error"
            break
        if posting is None:
            continue  # the user saved it in the meantime: theirs, never touched
        posting_id = posting.id  # read now: the object expires on a rollback
        counts["added"] += 1
        try:
            fit = await matching.analyze(db, llm, org_id=org_id, job_id=posting_id)
        except (QuotaExceeded, UpstreamUnavailable) as exc:
            # Take back the job this run added: no score, so no reason to clutter the inbox.
            await jobs.delete_job(db, org_id=org_id, job_id=posting_id)
            counts["added"] -= 1
            status = "partial"
            stop = "quota" if isinstance(exc, QuotaExceeded) else "ai_unavailable"
            break
        except Exception:
            await db.rollback()
            await jobs.delete_job(db, org_id=org_id, job_id=posting_id)
            raise  # run_search closes the run as internal_error
        counts["scored"] += 1
        keep = fit.score >= search.min_score
        await repository.add_result(
            db,
            org_id=org_id,
            search_id=search.id,
            source=provider.name,
            external_id=result.id,
            job_id=posting_id if keep else None,
            score=float(fit.score),
            status="new" if keep else "skipped",
            title=result.title,
            company=result.company,
            highlights=_highlights(fit.data),
        )
        if keep:
            counts["shortlisted"] += 1
        await repository.set_run_counts(run, counts)
        if keep:
            await db.commit()
        else:
            # A weak match is not worth the user's attention: it leaves the inbox (the ledger
            # keeps it, so it is never scored again). Only jobs this run added reach here.
            await jobs.delete_job(db, org_id=org_id, job_id=posting_id)
    else:
        if len(unseen) > budget:  # more to look at than today's budget allows
            stop = "limit" if budget == left_limit else "quota"
    return await _finish(db, run, search, now, status, stop, counts, error)


def _highlights(data: dict[str, Any]) -> dict[str, Any]:
    """A few short lines from the fit report: what is strong, what is weak, what is missing."""
    return {
        "strengths": [str(x) for x in data.get("strengths", [])][:3],
        "gaps": [str(x) for x in data.get("gaps", [])][:3],
        "missing": [str(x) for x in data.get("key_missing_requirements", [])][:5],
        "summary": data.get("summary"),
    }


async def _finish(
    db: AsyncSession,
    run: RadarRun,
    search: RadarSearch,
    now: datetime,
    status: str,
    stop: str,
    counts: dict[str, int],
    error: str | None = None,
) -> RadarRun:
    search.last_run_at = now
    await repository.finish_run(
        db, run, status=status, stop_reason=stop, error_code=error, **counts
    )
    await db.commit()
    return run


# ---- searches


async def create_search(
    db: AsyncSession, *, org_id: UUID, data: RadarSearchIn
) -> RadarSearch:
    if await repository.count_searches(db, org_id=org_id) >= MAX_SEARCHES_PER_ORG:
        raise ValidationFailed(f"You can have at most {MAX_SEARCHES_PER_ORG} radars.")
    values = data.model_dump()
    values["department"] = jobs.normalize_place(values["department"])
    values["contract_type"] = jobs.normalize_contracts(values["contract_type"])
    search = await repository.create_search(db, org_id=org_id, values=values)
    await db.commit()
    return search


async def list_searches(db: AsyncSession, *, org_id: UUID) -> list[RadarSearch]:
    return await repository.list_searches(db, org_id=org_id)


async def update_search(
    db: AsyncSession, *, org_id: UUID, search_id: UUID, changes: RadarSearchUpdate
) -> RadarSearch:
    search = await get_search(db, org_id=org_id, search_id=search_id)
    values = changes.model_dump(exclude_unset=True)
    if "name" in values and values["name"] is None:
        raise ValidationFailed("name cannot be null")
    for required in ("min_score", "daily_limit", "enabled"):
        if required in values and values[required] is None:
            raise ValidationFailed(f"{required} cannot be null")
    if "department" in values:  # "" or null clears it ("everywhere")
        values["department"] = jobs.normalize_place(values["department"])
    if "contract_type" in values:  # "" or null = all contracts
        values["contract_type"] = jobs.normalize_contracts(values["contract_type"])
    search = await repository.update_search(db, search, values)
    await db.commit()
    return search


async def delete_search(db: AsyncSession, *, org_id: UUID, search_id: UUID) -> None:
    search = await get_search(db, org_id=org_id, search_id=search_id)
    await repository.delete_search(db, search)
    await db.commit()


def is_interrupted(run: RadarRun | None, now: datetime) -> bool:
    """The run did not get to finish its work for a reason that is not the user's doing: the AI
    or the job source was down, something broke, or the worker died mid-run."""
    if run is None:
        return False
    if run.finished_at is None:
        return now - run.started_at >= STALE_RUN
    return run.status in ("partial", "error") and run.stop_reason in RETRYABLE_STOPS


PENDING_FOR = timedelta(
    minutes=2
)  # a requested run that has not started is "queued" this long


def run_refusal(
    search: RadarSearch, latest: RadarRun | None, now: datetime
) -> str | None:
    """Why "Run now" is not allowed yet, or None. A run that was asked for and has not started
    is never doubled. Otherwise a normal run waits out the cool-down, and one that was
    interrupted can be retried at once."""
    asked = search.requested_at
    if (
        asked is not None
        and now - asked < PENDING_FOR
        and (latest is None or latest.started_at < asked)
    ):
        return "A run has just been requested. Give it a moment."
    if is_interrupted(latest, now):
        return None
    last = search.last_run_at
    if last is not None and now - last < RUN_COOLDOWN:
        return "This radar just ran. Try again in a few minutes."
    return None


async def close_abandoned(
    db: AsyncSession, run: RadarRun | None, now: datetime
) -> RadarRun | None:
    """A run that never finished and is old enough to be abandoned (its worker was stopped) is
    closed as interrupted, so it can neither block a retry nor look "running" for ever."""
    if run is None or run.finished_at is not None or now - run.started_at < STALE_RUN:
        return run
    return await repository.finish_run(
        db,
        run,
        status="partial",
        stop_reason="worker_stopped",
        error_code="worker_stopped",
        found=run.found,
        added=run.added,
        scored=run.scored,
        shortlisted=run.shortlisted,
    )


async def request_run(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, search_id: UUID
) -> UUID:
    """Queue a run (task row + job in one transaction, ADR 0017). Refused if this search ran or
    started a run in the last few minutes ("Run now" cannot be used to drain the AI quota),
    unless its last run was interrupted: then it is simply retried."""
    search = await get_search(db, org_id=org_id, search_id=search_id)
    now = datetime.now(UTC)
    latest = await close_abandoned(
        db, await repository.latest_run(db, org_id=org_id, search_id=search.id), now
    )
    if reason := run_refusal(search, latest, now):
        raise ValidationFailed(reason)
    # Stamped at request time so the cool-down also covers a run that is queued but not started.
    search.last_run_at = search.requested_at = now
    task_run_id = await enqueue(
        db,
        task=RUN_TASK,
        org_id=org_id,
        kind="radar.run_search",
        task_kwargs={
            "org_id": str(org_id),
            "user_id": str(user_id),
            "search_id": str(search_id),
        },
    )
    await db.commit()
    return task_run_id


# ---- results and runs


@dataclass(frozen=True)
class ResultView:
    result: RadarResult
    search_name: str | None
    title: str | None
    company: str | None
    application_status: str | None


async def list_results(
    db: AsyncSession, *, org_id: UUID, status: str | None, limit: int, offset: int
) -> list[ResultView]:
    """Results with the search's name, the job's title and company (kept on the result, so
    they survive a removed job) and, once applied, the tracker status."""
    rows = await repository.list_results(
        db, org_id=org_id, status=status, limit=limit, offset=offset
    )
    job_ids = [r.job_id for r in rows if r.job_id is not None]
    names = await jobs.titles_for(db, org_id=org_id, job_ids=job_ids)
    statuses = await applications.statuses_for_jobs(db, org_id=org_id, job_ids=job_ids)
    searches = {s.id: s.name for s in await repository.list_searches(db, org_id=org_id)}
    views = []
    for r in rows:
        fallback = names.get(r.job_id, (None, None)) if r.job_id else (None, None)
        views.append(
            ResultView(
                result=r,
                search_name=searches.get(r.search_id),
                title=r.title or fallback[0],
                company=r.company or fallback[1],
                application_status=statuses.get(r.job_id) if r.job_id else None,
            )
        )
    return views


async def _new_result(
    db: AsyncSession, *, org_id: UUID, result_id: UUID
) -> RadarResult:
    result = await repository.get_result(db, org_id=org_id, result_id=result_id)
    if (
        result is None or result.status == "skipped"
    ):  # skipped = below the user's minimum
        raise NotFound("Radar result not found.")
    return result


async def approve(db: AsyncSession, *, org_id: UUID, result_id: UUID) -> None:
    """The user wants this one: it stays in their jobs for the letter and apply steps."""
    result = await _new_result(db, org_id=org_id, result_id=result_id)
    result.status = "approved"
    await db.commit()


async def dismiss(db: AsyncSession, *, org_id: UUID, result_id: UUID) -> None:
    """Not interested: the job leaves the user's jobs too, unless they already approved it (a
    letter or application may exist; those keep their own copy of what they need)."""
    result = await _new_result(db, org_id=org_id, result_id=result_id)
    if result.status == "new" and result.job_id is not None:
        await jobs.delete_job(db, org_id=org_id, job_id=result.job_id)
        result = await _new_result(db, org_id=org_id, result_id=result_id)
    result.status = "dismissed"
    await db.commit()


async def mark_seen(db: AsyncSession, *, org_id: UUID) -> None:
    """The user opened their matches: the menu badge goes back to zero until the next run."""
    await repository.mark_seen(db, org_id=org_id)
    await db.commit()


async def list_runs(db: AsyncSession, *, org_id: UUID, limit: int) -> list[RadarRun]:
    return await repository.list_runs(db, org_id=org_id, limit=limit)


# ---- the daily run (every user's enabled searches)


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=UTC)


async def due_searches(
    db: AsyncSession, *, now: datetime
) -> list[tuple[UUID, UUID, UUID]]:
    """``(search id, org id, owner user id)`` for enabled searches that have not run today, of
    owners who are neither blocked nor idle for 30 days."""
    searches = await repository.due_searches(
        db, ran_before=_day_start(now), limit=MAX_RUNS_PER_DAY
    )
    owners = await identity.active_owner_ids(
        db,
        org_ids=list({s.org_id for s in searches}),
        active_since=now - INACTIVE_AFTER,
    )
    return [(s.id, s.org_id, owners[s.org_id]) for s in searches if s.org_id in owners]


async def _run_each(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    llm_for: Callable[[AsyncSession, UUID, UUID], Awaitable[LLMGateway]],
    provider: JobProvider,
    targets: list[tuple[UUID, UUID, UUID]],
    *,
    quota: int,
    now: datetime,
) -> int:
    """Run each ``(search id, org id, owner user id)`` in its own session, one after another,
    so one failure cannot touch the others. Returns how many runs were started."""
    started = 0
    for search_id, org_id, user_id in targets:
        async with session_factory() as session:
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
            except Exception as exc:  # noqa: BLE001  (e.g. the search was deleted meanwhile)
                logger.error(
                    "radar background run failed",
                    extra={"error_type": type(exc).__name__},
                )
                continue
            started += run is not None
    return started


async def run_due_searches(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    llm_for: Callable[[AsyncSession, UUID, UUID], Awaitable[LLMGateway]],
    provider: JobProvider,
    *,
    quota: int,
    now: datetime | None = None,
) -> int:
    """The daily run: every due search once."""
    now = now or datetime.now(UTC)
    async with session_factory() as session:
        due = await due_searches(session, now=now)
    return await _run_each(
        session_factory, llm_for, provider, due, quota=quota, now=now
    )


async def interrupted_searches(
    db: AsyncSession, *, now: datetime
) -> list[tuple[UUID, UUID, UUID]]:
    """Daily searches whose latest run today was interrupted, a while ago, and that have not used
    their automatic retries: the AI or the job source was down, so the work is simply tried again.
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
    searches = [
        s for s in await repository.searches_by_ids(db, search_ids=wanted) if s.enabled
    ]
    owners = await identity.active_owner_ids(
        db,
        org_ids=list({s.org_id for s in searches}),
        active_since=now - INACTIVE_AFTER,
    )
    return [(s.id, s.org_id, owners[s.org_id]) for s in searches if s.org_id in owners]


async def retry_interrupted_searches(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    llm_for: Callable[[AsyncSession, UUID, UUID], Awaitable[LLMGateway]],
    provider: JobProvider,
    *,
    quota: int,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    async with session_factory() as session:
        targets = await interrupted_searches(session, now=now)
    return await _run_each(
        session_factory, llm_for, provider, targets, quota=quota, now=now
    )


async def new_match_lines(db: AsyncSession, *, now: datetime) -> dict[UUID, list[str]]:
    """Digest lines per org: how many new shortlisted jobs since yesterday, and the best three."""
    since = now - timedelta(days=1)
    counts = await repository.new_counts_since(db, since=since)
    best = await repository.top_new_since(db, since=since, per_org=3)
    lines: dict[UUID, list[str]] = {}
    for org_id, n in counts.items():
        head = (
            f"- {n} new job{'s' if n > 1 else ''} match your radar / "
            f"{n} nouvelle{'s' if n > 1 else ''} offre{'s' if n > 1 else ''} pour votre radar"
        )
        top = [
            f"    · {r.title or 'Job'}, {r.company or '?'} ({round(r.score or 0)}%)"
            for r in best.get(org_id, [])
        ]
        lines[org_id] = [head, *top]
    return lines


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, object]]]:
    searches, results, runs = await repository.all_for_org(db, org_id=org_id)
    return {
        "radar_searches": rows_as_dicts(searches),
        "radar_results": rows_as_dicts(results),
        "radar_runs": rows_as_dicts(runs),
    }


async def ai_use_today(
    db: AsyncSession, *, user_id: UUID, quota: int
) -> tuple[int, int, int]:
    """``(used, quota, radar_stops_at)``: the radar stops once ``QUOTA_RESERVE`` calls are left."""
    used = await usage.count_calls_today(db, user_id=user_id)
    return used, quota, max(quota - QUOTA_RESERVE, 0)


async def sweep_old_runs(db: AsyncSession, *, cutoff: datetime) -> int:
    deleted = await repository.delete_runs_older_than(db, cutoff=cutoff)
    await db.commit()
    return deleted


# ---- seeing and following the radar


def next_daily_run(now: datetime) -> datetime:
    """The next scheduled run (06:30 UTC; keep in step with the cron in ``tasks.py``)."""
    today = datetime.combine(now.date(), DAILY_RUN_AT, tzinfo=UTC)
    return today if today > now else today + timedelta(days=1)


async def status(db: AsyncSession, *, org_id: UUID, now: datetime) -> dict[str, Any]:
    """What the user wants at a glance: new matches, whether it is working, last and next run."""
    searches = await repository.list_searches(db, org_id=org_id)
    runs = await repository.list_runs(db, org_id=org_id, limit=1)
    last = runs[0] if runs else None
    daily = [s for s in searches if s.enabled]
    return {
        "new_matches": await repository.count_new(db, org_id=org_id),
        "searches": len(searches),
        "daily_searches": len(daily),
        "running": last is not None
        and last.finished_at is None
        and now - last.started_at < STALE_RUN,
        "last_run": last,
        "next_run_at": next_daily_run(now) if daily else None,
        "interrupted": is_interrupted(last, now),
        "interrupted_reason": (
            None
            if not is_interrupted(last, now) or last is None
            else (last.stop_reason if last.finished_at else "stalled")
        ),
    }


_APPLIED = {"applied", "in_review", "interview", "offer", "rejected", "ghosted"}


async def insights(
    db: AsyncSession, *, org_id: UUID, now: datetime, days: int = 30
) -> dict[str, Any]:
    """The radar's story over ``days``: how many it scored, kept, how many the user approved,
    applied to and got interviews for, and which requirements are missing most often."""
    rows = await repository.results_since(
        db, org_id=org_id, since=now - timedelta(days=days)
    )
    kept = [r for r in rows if r.status != "skipped"]
    statuses = await applications.statuses_for_jobs(
        db, org_id=org_id, job_ids=[r.job_id for r in kept if r.job_id is not None]
    )
    seen: dict[str, int] = {}
    for r in rows:
        for text in (r.highlights or {}).get("missing", []):
            key = str(text).strip().lower()
            if key:
                seen[key] = seen.get(key, 0) + 1
    scores = [r.score for r in rows if r.score is not None]
    return {
        "days": days,
        "funnel": {
            "scored": len(rows),
            "shortlisted": len(kept),
            "approved": sum(r.status == "approved" for r in kept),
            "applied": sum(
                statuses.get(r.job_id, "") in _APPLIED for r in kept if r.job_id
            ),
            "interviews": sum(
                statuses.get(r.job_id, "") in {"interview", "offer"}
                for r in kept
                if r.job_id
            ),
        },
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "most_missing": [
            {"text": t, "count": n}
            for t, n in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
            if n >= 2
        ][:5],
    }


async def keep_anyway(
    db: AsyncSession, provider: JobProvider, *, org_id: UUID, result_id: UUID
) -> UUID:
    """The user disagrees with a rejection: put that job in their jobs (no model call; they can
    run the fit report themselves) and mark the result approved."""
    result = await repository.get_result(db, org_id=org_id, result_id=result_id)
    if result is None or result.status != "skipped":
        raise NotFound("Radar result not found.")
    posting = await jobs.save_new_search_result(
        db, provider, org_id=org_id, external_id=result.external_id
    )
    if posting is None:  # they already had it
        posting = await jobs.find_by_external(
            db, org_id=org_id, source=result.source, external_id=result.external_id
        )
    if posting is None:
        raise NotFound("Radar result not found.")
    result.job_id, result.status = posting.id, "approved"
    await db.commit()
    return posting.id
