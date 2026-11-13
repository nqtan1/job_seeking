"""All SQL for the cvreview module. Every query filters by org_id."""

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.tasks import TaskRun
from recruitai.modules.cvreview.models import CvReview
from recruitai.modules.cvreview.schemas import SCHEMA_VERSION, ReviewData


async def add(
    session: AsyncSession,
    *,
    org_id: UUID,
    document_id: UUID | None,
    parent_id: UUID | None,
    track: str,
    level: str,
    score: int,
    data: ReviewData,
    model: str,
    prompt_version: str,
) -> CvReview:
    row = CvReview(
        org_id=org_id,
        document_id=document_id,
        parent_id=parent_id,
        track=track,
        level=level,
        score=score,
        data=data.model_dump(mode="json"),
        schema_version=SCHEMA_VERSION,
        model=model,
        prompt_version=prompt_version,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)  # server-side created_at
    return row


async def get(
    session: AsyncSession, *, org_id: UUID, review_id: UUID
) -> CvReview | None:
    return (
        await session.execute(
            select(CvReview).where(CvReview.org_id == org_id, CvReview.id == review_id)
        )
    ).scalar_one_or_none()


async def list_for_org(
    session: AsyncSession, *, org_id: UUID, limit: int, offset: int
) -> list[CvReview]:
    rows = await session.execute(
        select(CvReview)
        .where(CvReview.org_id == org_id)
        .order_by(CvReview.created_at.desc(), CvReview.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


async def delete(session: AsyncSession, *, org_id: UUID, review_id: UUID) -> bool:
    stmt = sa_delete(CvReview).where(
        CvReview.org_id == org_id, CvReview.id == review_id
    )
    return (await session.execute(stmt.returning(CvReview.id))).first() is not None


async def count_for_org(session: AsyncSession, *, org_id: UUID) -> int:
    """Stored reviews plus queued ones, after taking a per-org lock (released at commit): two
    simultaneous requests cannot both see room for the last slot."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(f"cvr:{org_id}", 0)))
    )
    stored = select(func.count()).select_from(CvReview).where(CvReview.org_id == org_id)
    queued = (
        select(func.count())
        .select_from(TaskRun)
        .where(
            TaskRun.org_id == org_id,
            TaskRun.kind == "cvreview.evaluate",
            TaskRun.status == "queued",
        )
    )
    return (
        await session.execute(
            select(stored.scalar_subquery() + queued.scalar_subquery())
        )
    ).scalar_one()


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[CvReview]:
    rows = await session.execute(
        select(CvReview).where(CvReview.org_id == org_id).order_by(CvReview.created_at)
    )
    return list(rows.scalars())
