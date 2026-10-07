"""All SQL for the jobs module. ``job_postings`` queries filter by ``org_id``;
``job_search_cache`` is shared public data (see models.py)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.ids import new_id
from recruitai.modules.jobs.models import JobPosting, JobSearchCache
from recruitai.modules.jobs.schemas import SCHEMA_VERSION, JobPosition


async def get(
    session: AsyncSession, *, org_id: UUID, job_id: UUID
) -> JobPosting | None:
    return (
        await session.execute(
            select(JobPosting).where(
                JobPosting.org_id == org_id, JobPosting.id == job_id
            )
        )
    ).scalar_one_or_none()


async def list_for_org(
    session: AsyncSession, *, org_id: UUID, limit: int, offset: int
) -> list[JobPosting]:
    rows = await session.execute(
        select(JobPosting)
        .where(JobPosting.org_id == org_id)
        .order_by(JobPosting.created_at.desc(), JobPosting.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


async def add(
    session: AsyncSession,
    *,
    org_id: UUID,
    source: str,
    external_id: str | None,
    info: JobPosition,
) -> JobPosting:
    """Insert; saving the same ``(source, external_id)`` again returns the existing row
    (atomic on the unique constraint, so a double click can't create two)."""
    values = {
        "title": info.title,
        "company": info.company.name,
        "data": info.model_dump(mode="json"),
        "schema_version": SCHEMA_VERSION,
    }
    inserted = await _insert(session, org_id, source, external_id, values)
    if inserted is not None:
        return inserted
    return (
        await session.execute(
            select(JobPosting).where(
                JobPosting.org_id == org_id,
                JobPosting.source == source,
                JobPosting.external_id == external_id,
            )
        )
    ).scalar_one()


async def add_new(
    session: AsyncSession,
    *,
    org_id: UUID,
    source: str,
    external_id: str,
    info: JobPosition,
) -> JobPosting | None:
    """Like ``add`` but returns None when the org already had this offer, so a caller that may
    delete what it added (the radar) can tell its own rows from the user's."""
    values = {
        "title": info.title,
        "company": info.company.name,
        "data": info.model_dump(mode="json"),
        "schema_version": SCHEMA_VERSION,
    }
    return await _insert(session, org_id, source, external_id, values)


async def _insert(
    session: AsyncSession,
    org_id: UUID,
    source: str,
    external_id: str | None,
    values: dict[str, Any],
) -> JobPosting | None:
    return (
        await session.execute(
            insert(JobPosting)
            .values(
                id=new_id(),
                org_id=org_id,
                source=source,
                external_id=external_id,
                **values,
            )
            .on_conflict_do_nothing()
            .returning(JobPosting)
        )
    ).scalar_one_or_none()


async def cache_get(
    session: AsyncSession, *, key: str, now: datetime
) -> dict[str, Any] | None:
    """The cached payload if it has not expired (expiry instant itself counts as expired)."""
    return (
        await session.execute(
            select(JobSearchCache.payload).where(
                JobSearchCache.key == key, JobSearchCache.expires_at > now
            )
        )
    ).scalar_one_or_none()


async def cache_put(
    session: AsyncSession,
    *,
    key: str,
    provider: str,
    payload: dict[str, Any],
    expires_at: datetime,
) -> None:
    await session.execute(
        insert(JobSearchCache)
        .values(key=key, provider=provider, payload=payload, expires_at=expires_at)
        .on_conflict_do_update(
            index_elements=[JobSearchCache.key],
            set_={"payload": payload, "expires_at": expires_at},
        )
    )


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[JobPosting]:
    """Every job of the org, for the data export (no paging: the user asked for everything)."""
    rows = await session.execute(
        select(JobPosting)
        .where(JobPosting.org_id == org_id)
        .order_by(JobPosting.created_at)
    )
    return list(rows.scalars())


async def delete_expired_cache(session: AsyncSession, *, now: datetime) -> int:
    result = await session.execute(
        delete(JobSearchCache).where(JobSearchCache.expires_at <= now)
    )
    return result.rowcount or 0  # type: ignore[attr-defined]


async def known_external_ids(
    session: AsyncSession, *, org_id: UUID, source: str, external_ids: list[str]
) -> set[str]:
    """Which of these offers the org already has in its inbox."""
    if not external_ids:
        return set()
    rows = await session.execute(
        select(JobPosting.external_id).where(
            JobPosting.org_id == org_id,
            JobPosting.source == source,
            JobPosting.external_id.in_(external_ids),
        )
    )
    return {e for e in rows.scalars() if e}


async def delete_one(session: AsyncSession, *, org_id: UUID, job_id: UUID) -> None:
    await session.execute(
        delete(JobPosting).where(JobPosting.org_id == org_id, JobPosting.id == job_id)
    )  # its fit analyses go with it (ON DELETE CASCADE)


async def titles_for(
    session: AsyncSession, *, org_id: UUID, job_ids: list[UUID]
) -> dict[UUID, tuple[str, str | None]]:
    """``{job id: (title, company)}`` for the org's jobs among ``job_ids``."""
    if not job_ids:
        return {}
    rows = await session.execute(
        select(JobPosting.id, JobPosting.title, JobPosting.company).where(
            JobPosting.org_id == org_id, JobPosting.id.in_(job_ids)
        )
    )
    return {i: (t, c) for i, t, c in rows.all()}


async def find_by_external(
    session: AsyncSession, *, org_id: UUID, source: str, external_id: str
) -> JobPosting | None:
    return (
        await session.execute(
            select(JobPosting).where(
                JobPosting.org_id == org_id,
                JobPosting.source == source,
                JobPosting.external_id == external_id,
            )
        )
    ).scalar_one_or_none()
