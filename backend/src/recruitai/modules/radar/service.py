"""The job radar (ADR 0021): search -> skip what is known -> score -> shortlist.

It only proposes. Model calls are the fit analyses through the tenant-bound gateway (the daily AI
quota applies; ``QUOTA_RESERVE`` calls are left for the user). Shortlisting is decided by code
(score >= the user's minimum). No FastAPI imports.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import usage
from recruitai.core.errors import Conflict, NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.tasks import enqueue
from recruitai.modules.applications import service as applications
from recruitai.modules.jobs import service as jobs
from recruitai.modules.jobs.providers.base import JobProvider
from recruitai.modules.radar import repository
from recruitai.modules.radar.consent import (
    apply_link,
    consented_orgs,
    get_consent,
    grant_consent,
    withdraw_consent,
    withdraw_link,
)
from recruitai.modules.radar.models import RadarResult, RadarRun, RadarSearch
from recruitai.modules.radar.runs import (
    QUOTA_RESERVE,
    STALE_RUN,
    get_search,
    is_interrupted,
    run_search,
)
from recruitai.modules.radar.schedule import (
    Notify,
    due_searches,
    interrupted_searches,
    new_match_lines,
    pause_inactive,
    retry_interrupted_searches,
    run_due_searches,
)
from recruitai.modules.radar.schemas import (
    MAX_SEARCHES_PER_ORG,
    RadarSearchIn,
    RadarSearchUpdate,
)

# Moved to runs.py, schedule.py and consent.py; still reached through this module.
__all__ = [
    "Notify",
    "apply_link",
    "due_searches",
    "get_consent",
    "grant_consent",
    "interrupted_searches",
    "new_match_lines",
    "pause_inactive",
    "retry_interrupted_searches",
    "run_due_searches",
    "run_search",
    "withdraw_consent",
    "withdraw_link",
]

DAILY_RUN_AT = time(6, 30)  # UTC; the cron in tasks.py
RUN_COOLDOWN = timedelta(minutes=5)  # between two "Run now" of the same search
RUN_TASK = "radar:run_search"  # registered by the worker (worker.py, namespace "radar")


# searches


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


PENDING_FOR = timedelta(
    minutes=2
)  # a requested run that has not started is "queued" this long


def run_refusal(
    search: RadarSearch, latest: RadarRun | None, now: datetime
) -> str | None:
    """Why "Run now" is not allowed yet, or None. Never doubles a queued run; interrupted runs retry
    at once, others wait out the cool-down."""
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
    """Queue a run (task row + job in one transaction, ADR 0017). Refused within the cool-down so
    "Run now" cannot drain the AI quota, unless the last run was interrupted."""
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


# results and runs


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


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, object]]]:
    searches, results, runs = await repository.all_for_org(db, org_id=org_id)
    return {
        "consents": rows_as_dicts(
            await repository.consent_history(db, org_id=org_id, limit=10_000)
        ),
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


# seeing and following the radar


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


# Lifecycle: resume, inactivity, public links (ADR 0024)


async def resume(
    db: AsyncSession, *, org_id: UUID, policy_version: str
) -> list[RadarSearch]:
    """Release radars held for inactivity or repeated failures. Needs a current consent: a
    resume must never be a way around it."""
    if org_id not in await consented_orgs(
        db, org_ids=[org_id], policy_version=policy_version
    ):
        raise Conflict("Radar consent is needed first.", code="consent_required")
    for reason in ("inactive", "failures"):
        await repository.release_org_searches(db, org_id=org_id, reason=reason)
    await repository.reset_failures(db, org_id=org_id)
    await db.commit()
    return await repository.list_searches(db, org_id=org_id)
