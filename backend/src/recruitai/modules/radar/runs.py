"""One radar run: search -> skip what is known -> score -> shortlist (ADR 0021)."""

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import usage
from recruitai.ai.gateway import LLMGateway, QuotaExceeded
from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.core.language import Language
from recruitai.modules.candidates import service as candidates
from recruitai.modules.identity import service as identity
from recruitai.modules.jobs import service as jobs
from recruitai.modules.jobs.providers.base import JobProvider
from recruitai.modules.jobs.schemas import UnifiedJobSearchResult
from recruitai.modules.matching import service as matching
from recruitai.modules.radar import repository
from recruitai.modules.radar.models import RadarRun, RadarSearch

logger = logging.getLogger(__name__)

QUOTA_RESERVE = (
    15  # model calls per day left for the user's own chat, letters, fit checks
)
STALE_RUN = timedelta(
    minutes=10
)  # an unfinished run older than this is treated as abandoned (the worker died)
# A run that stopped for a reason that is not the user's doing can simply be tried again.
RETRYABLE_STOPS = {
    "ai_unavailable",
    "provider_error",
    "internal_error",
    "worker_stopped",
}
MAX_AI_CALLS_PER_RUN = (
    30  # one fit analysis per scored offer: a hard ceiling per run (ADR 0024)
)


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
    """One run of one search. Returns None, writing nothing, if another run is in progress; otherwise
    always leaves a ``radar_runs`` row saying why it stopped."""
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
    budget = min(left_limit, left_quota, MAX_AI_CALLS_PER_RUN)
    language = await identity.user_language(db, user_id)
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

    outcome = await _score_offers(
        db, llm, provider, run, search, fresh, language, counts
    )
    if outcome is None:
        if len(unseen) > budget:  # more to look at than today's budget allows
            stop = "limit" if budget == left_limit else "quota"
    else:
        status, stop, error = outcome
    return await _finish(db, run, search, now, status, stop, counts, error)


async def _score_offers(
    db: AsyncSession,
    llm: LLMGateway,
    provider: JobProvider,
    run: RadarRun,
    search: RadarSearch,
    fresh: list[UnifiedJobSearchResult],
    language: Language,
    counts: dict[str, int],
) -> tuple[str, str, str | None] | None:
    """Save, score and shortlist each fresh offer. Returns (status, stop, error) when the run had
    to stop early, None when every offer was looked at."""
    org_id = search.org_id
    for result in fresh:
        try:
            posting = await jobs.save_new_search_result(
                db, provider, org_id=org_id, external_id=result.id
            )
        except NotFound:
            continue  # the offer was withdrawn since the search
        except UpstreamUnavailable:
            return "partial", "provider_error", "provider_error"
        if posting is None:
            continue  # the user saved it in the meantime: theirs, never touched
        posting_id = posting.id  # read now: the object expires on a rollback
        counts["added"] += 1
        try:
            fit = await matching.analyze(
                db, llm, org_id=org_id, job_id=posting_id, language=language
            )
        except (QuotaExceeded, UpstreamUnavailable) as exc:
            # Take back the job this run added: no score, so no reason to clutter the inbox.
            await jobs.delete_job(db, org_id=org_id, job_id=posting_id)
            counts["added"] -= 1
            stop = "quota" if isinstance(exc, QuotaExceeded) else "ai_unavailable"
            return "partial", stop, None
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
    return None


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


def is_interrupted(run: RadarRun | None, now: datetime) -> bool:
    """The run did not get to finish its work for a reason that is not the user's doing: the AI
    or the job source was down, something broke, or the worker died mid-run."""
    if run is None:
        return False
    if run.finished_at is None:
        return now - run.started_at >= STALE_RUN
    return run.status in ("partial", "error") and run.stop_reason in RETRYABLE_STOPS
