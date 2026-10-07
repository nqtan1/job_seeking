"""All SQL for the radar module. Every query filters by org_id."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.radar.models import RadarResult, RadarRun, RadarSearch

# ---- searches


async def count_searches(session: AsyncSession, *, org_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(RadarSearch)
            .where(RadarSearch.org_id == org_id)
        )
    ).scalar_one()


async def create_search(
    session: AsyncSession, *, org_id: UUID, values: dict[str, Any]
) -> RadarSearch:
    search = RadarSearch(org_id=org_id, **values)
    session.add(search)
    await session.flush()
    await session.refresh(search)  # server-side created_at / updated_at
    return search


async def get_search(
    session: AsyncSession, *, org_id: UUID, search_id: UUID
) -> RadarSearch | None:
    return (
        await session.execute(
            select(RadarSearch).where(
                RadarSearch.org_id == org_id, RadarSearch.id == search_id
            )
        )
    ).scalar_one_or_none()


async def list_searches(session: AsyncSession, *, org_id: UUID) -> list[RadarSearch]:
    rows = await session.execute(
        select(RadarSearch)
        .where(RadarSearch.org_id == org_id)
        .order_by(RadarSearch.created_at, RadarSearch.id)
    )
    return list(rows.scalars())


async def update_search(
    session: AsyncSession, search: RadarSearch, changes: dict[str, Any]
) -> RadarSearch:
    for field, value in changes.items():
        setattr(search, field, value)
    await session.flush()
    await session.refresh(search)
    return search


async def delete_search(session: AsyncSession, search: RadarSearch) -> None:
    await session.delete(search)  # results and runs go with it (ON DELETE CASCADE)
    await session.flush()


# ---- results (also the "seen" ledger)


async def seen_external_ids(
    session: AsyncSession, *, org_id: UUID, source: str, external_ids: list[str]
) -> set[str]:
    if not external_ids:
        return set()
    rows = await session.execute(
        select(RadarResult.external_id).where(
            RadarResult.org_id == org_id,
            RadarResult.source == source,
            RadarResult.external_id.in_(external_ids),
        )
    )
    return set(rows.scalars())


async def add_result(
    session: AsyncSession,
    *,
    org_id: UUID,
    search_id: UUID,
    source: str,
    external_id: str,
    job_id: UUID | None,
    score: float | None,
    status: str,
    title: str | None = None,
    company: str | None = None,
    highlights: dict[str, Any] | None = None,
) -> bool:
    """Idempotent on (org, source, external id): returns whether a new row was written."""
    inserted = (
        await session.execute(
            pg_insert(RadarResult)
            .values(
                org_id=org_id,
                search_id=search_id,
                source=source,
                external_id=external_id,
                job_id=job_id,
                score=score,
                status=status,
                title=title,
                company=company,
                highlights=highlights,
            )
            .on_conflict_do_nothing(index_elements=["org_id", "source", "external_id"])
            .returning(RadarResult.id)
        )
    ).scalar_one_or_none()
    return inserted is not None


async def list_results(
    session: AsyncSession,
    *,
    org_id: UUID,
    status: str | None,
    limit: int,
    offset: int,
) -> list[RadarResult]:
    stmt = select(RadarResult).where(
        RadarResult.org_id == org_id,
        # a shortlisted result whose job the user has since deleted is a dead entry
        (RadarResult.status != "new") | (RadarResult.job_id.is_not(None)),
    )
    if status is not None:
        stmt = stmt.where(RadarResult.status == status)
    rows = await session.execute(
        stmt.order_by(
            RadarResult.score.desc().nulls_last(), RadarResult.found_at.desc()
        )
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


async def get_result(
    session: AsyncSession, *, org_id: UUID, result_id: UUID
) -> RadarResult | None:
    return (
        await session.execute(
            select(RadarResult).where(
                RadarResult.org_id == org_id, RadarResult.id == result_id
            )
        )
    ).scalar_one_or_none()


async def scored_since(
    session: AsyncSession, *, org_id: UUID, search_id: UUID, since: datetime
) -> int:
    """Jobs this search has looked at since ``since`` (the daily limit is counted on these)."""
    return (
        await session.execute(
            select(func.count())
            .select_from(RadarResult)
            .where(
                RadarResult.org_id == org_id,
                RadarResult.search_id == search_id,
                RadarResult.found_at >= since,
            )
        )
    ).scalar_one()


# ---- runs


async def start_run(
    session: AsyncSession, *, org_id: UUID, search_id: UUID
) -> RadarRun:
    run = RadarRun(org_id=org_id, search_id=search_id)
    session.add(run)
    await session.flush()
    return run


async def finish_run(
    session: AsyncSession,
    run: RadarRun,
    *,
    status: str,
    stop_reason: str,
    found: int,
    added: int,
    scored: int,
    shortlisted: int,
    error_code: str | None = None,
) -> RadarRun:
    run.status = status
    run.stop_reason = stop_reason
    run.found, run.added = found, added
    run.scored, run.shortlisted = scored, shortlisted
    run.error_code = error_code
    run.finished_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(run)
    return run


async def other_run_in_progress(
    session: AsyncSession,
    *,
    org_id: UUID,
    search_id: UUID,
    since: datetime,
) -> bool:
    """Is another run of this search unfinished and recent (not abandoned)?"""
    found = (
        await session.execute(
            select(RadarRun.id)
            .where(
                RadarRun.org_id == org_id,
                RadarRun.search_id == search_id,
                RadarRun.finished_at.is_(None),
                RadarRun.started_at >= since,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def list_runs(
    session: AsyncSession, *, org_id: UUID, limit: int
) -> list[RadarRun]:
    rows = await session.execute(
        select(RadarRun)
        .where(RadarRun.org_id == org_id)
        .order_by(RadarRun.started_at.desc(), RadarRun.id)
        .limit(limit)
    )
    return list(rows.scalars())


async def due_searches(
    session: AsyncSession, *, ran_before: datetime, limit: int
) -> list[RadarSearch]:
    """Enabled searches that have not run since ``ran_before`` (every org)."""
    rows = await session.execute(
        select(RadarSearch)
        .where(
            RadarSearch.enabled.is_(True),
            (RadarSearch.last_run_at.is_(None))
            | (RadarSearch.last_run_at < ran_before),
        )
        .order_by(RadarSearch.last_run_at.asc().nulls_first(), RadarSearch.id)
        .limit(limit)
    )
    return list(rows.scalars())


async def new_counts_since(
    session: AsyncSession, *, since: datetime
) -> dict[UUID, int]:
    """``{org id: shortlisted results found since}`` for the digest email."""
    rows = await session.execute(
        select(RadarResult.org_id, func.count())
        .where(RadarResult.status == "new", RadarResult.found_at >= since)
        .group_by(RadarResult.org_id)
    )
    return {org_id: n for org_id, n in rows.all()}


async def all_for_org(
    session: AsyncSession, *, org_id: UUID
) -> tuple[list[RadarSearch], list[RadarResult], list[RadarRun]]:
    searches = await list_searches(session, org_id=org_id)
    results = (
        await session.execute(
            select(RadarResult)
            .where(RadarResult.org_id == org_id)
            .order_by(RadarResult.found_at)
        )
    ).scalars()
    runs = (
        await session.execute(
            select(RadarRun)
            .where(RadarRun.org_id == org_id)
            .order_by(RadarRun.started_at)
        )
    ).scalars()
    return searches, list(results), list(runs)


async def delete_runs_older_than(session: AsyncSession, *, cutoff: datetime) -> int:
    """Retention sweep for the activity log (finished runs only; the seen ledger is kept)."""
    result = await session.execute(
        sql_delete(RadarRun).where(
            RadarRun.finished_at.is_not(None), RadarRun.started_at < cutoff
        )
    )
    return result.rowcount or 0  # type: ignore[attr-defined]  # a DML result always has rowcount


async def set_run_counts(run: RadarRun, counts: dict[str, int]) -> None:
    """Live progress: the caller's next commit publishes it (the page polls the run)."""
    run.found, run.added = counts["found"], counts["added"]
    run.scored, run.shortlisted = counts["scored"], counts["shortlisted"]


async def count_new(session: AsyncSession, *, org_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(RadarResult)
            .where(
                RadarResult.org_id == org_id,
                RadarResult.status == "new",
                RadarResult.job_id.is_not(None),
                RadarResult.seen_at.is_(None),
            )
        )
    ).scalar_one()


async def mark_seen(session: AsyncSession, *, org_id: UUID) -> None:
    await session.execute(
        update(RadarResult)
        .where(RadarResult.org_id == org_id, RadarResult.seen_at.is_(None))
        .values(seen_at=func.now())
    )


async def results_since(
    session: AsyncSession, *, org_id: UUID, since: datetime
) -> list[RadarResult]:
    rows = await session.execute(
        select(RadarResult).where(
            RadarResult.org_id == org_id, RadarResult.found_at >= since
        )
    )
    return list(rows.scalars())


async def top_new_since(
    session: AsyncSession, *, since: datetime, per_org: int
) -> dict[UUID, list[RadarResult]]:
    """The best new matches per org since ``since`` (for the digest email)."""
    rows = await session.execute(
        select(RadarResult)
        .where(
            RadarResult.status == "new",
            RadarResult.job_id.is_not(None),
            RadarResult.found_at >= since,
        )
        .order_by(RadarResult.score.desc().nulls_last())
    )
    out: dict[UUID, list[RadarResult]] = {}
    for r in rows.scalars():
        bucket = out.setdefault(r.org_id, [])
        if len(bucket) < per_org:
            bucket.append(r)
    return out


async def latest_run(
    session: AsyncSession, *, org_id: UUID, search_id: UUID
) -> RadarRun | None:
    return (
        await session.execute(
            select(RadarRun)
            .where(RadarRun.org_id == org_id, RadarRun.search_id == search_id)
            .order_by(RadarRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def runs_since(session: AsyncSession, *, since: datetime) -> list[RadarRun]:
    """Every run (all orgs) since ``since``, oldest first: for the automatic retry."""
    rows = await session.execute(
        select(RadarRun)
        .where(RadarRun.started_at >= since)
        .order_by(RadarRun.started_at)
    )
    return list(rows.scalars())


async def searches_by_ids(
    session: AsyncSession, *, search_ids: list[UUID]
) -> list[RadarSearch]:
    if not search_ids:
        return []
    rows = await session.execute(
        select(RadarSearch).where(RadarSearch.id.in_(search_ids))
    )
    return list(rows.scalars())
