"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import LLMGateway
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.errors import (
    NotFound,
    Unauthorized,
    UpstreamUnavailable,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.ratelimit import limit_ai
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.matching import service
from recruitai.modules.matching.models import FitAnalysis
from recruitai.modules.matching.schemas import (
    CompanyType,
    FitAnalysisIn,
    FitAnalysisOut,
    FitCheck,
    Recommendation,
)

router = APIRouter(prefix="/api/v1/fit-analyses", tags=["matching"])


def _out(row: FitAnalysis) -> FitAnalysisOut:
    company_type: CompanyType = row.company_type  # type: ignore[assignment]  # DB CHECK
    return FitAnalysisOut(
        id=row.id,
        job_id=row.job_id,
        candidate_id=row.candidate_id,
        company_type=company_type,
        score=row.score,
        verdict=Recommendation(row.verdict),
        data=FitCheck.model_validate(row.data),
        model=row.model,
        prompt_version=row.prompt_version,
        created_at=row.created_at,
    )


@router.post(
    "",
    status_code=201,
    response_model=FitAnalysisOut,
    # App Check: every fit analysis costs an LLM call (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def create_fit_analysis(
    body: FitAnalysisIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> FitAnalysisOut:
    row = await service.analyze(
        db,
        llm,
        org_id=ctx.org_id,
        job_id=body.job_id,
        company_type=body.company_type,
    )
    return _out(row)


@router.get(
    "",
    response_model=list[FitAnalysisOut],
    responses=problem_responses(Unauthorized),
)
async def list_fit_analyses(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    job_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FitAnalysisOut]:
    rows = await service.list_analyses(
        db, org_id=ctx.org_id, job_id=job_id, limit=limit, offset=offset
    )
    return [_out(r) for r in rows]
