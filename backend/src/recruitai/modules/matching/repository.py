"""All SQL for the matching module. Every query filters by org_id."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.matching.models import FitAnalysis
from recruitai.modules.matching.schemas import SCHEMA_VERSION, FitCheck


async def add(
    session: AsyncSession,
    *,
    org_id: UUID,
    candidate_id: UUID,
    job_id: UUID,
    company_type: str,
    check: FitCheck,
    model: str,
    prompt_version: str,
) -> FitAnalysis:
    row = FitAnalysis(
        org_id=org_id,
        candidate_id=candidate_id,
        job_id=job_id,
        company_type=company_type,
        score=check.fit_score,
        verdict=check.recommendation.value,
        data=check.model_dump(mode="json"),
        schema_version=SCHEMA_VERSION,
        model=model,
        prompt_version=prompt_version,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)  # server-side created_at
    return row


async def list_for_org(
    session: AsyncSession,
    *,
    org_id: UUID,
    job_id: UUID | None,
    limit: int,
    offset: int,
) -> list[FitAnalysis]:
    stmt = select(FitAnalysis).where(FitAnalysis.org_id == org_id)
    if job_id is not None:
        stmt = stmt.where(FitAnalysis.job_id == job_id)
    rows = await session.execute(
        stmt.order_by(FitAnalysis.created_at.desc(), FitAnalysis.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[FitAnalysis]:
    rows = await session.execute(
        select(FitAnalysis)
        .where(FitAnalysis.org_id == org_id)
        .order_by(FitAnalysis.created_at)
    )
    return list(rows.scalars())
