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
from recruitai.core.storage import Storage, get_storage_dependency
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.jobs import service
from recruitai.modules.jobs.models import JobPosting
from recruitai.modules.jobs.providers.base import JobProvider
from recruitai.modules.jobs.providers.factory import france_travail_provider
from recruitai.modules.jobs.schemas import (
    FileJobIn,
    JobIn,
    JobOut,
    JobPosition,
    JobSource,
    ManualJobIn,
    UnifiedJobSearchResponse,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def get_job_provider() -> JobProvider:
    return france_travail_provider()


def _out(job: JobPosting) -> JobOut:
    source: JobSource = job.source  # type: ignore[assignment]  # the DB CHECK enforces the three values
    return JobOut(
        id=job.id,
        source=source,
        external_id=job.external_id,
        data=JobPosition.model_validate(job.data),
        schema_version=job.schema_version,
        created_at=job.created_at,
    )


@router.post(
    "",
    status_code=201,
    response_model=JobOut,
    # App Check: manual and file jobs cost an LLM call (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def add_job(
    body: JobIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
    provider: Annotated[JobProvider, Depends(get_job_provider)],
) -> JobOut:
    if isinstance(body, ManualJobIn):
        job = await service.add_manual(db, llm, org_id=ctx.org_id, text=body.text)
    elif isinstance(body, FileJobIn):
        job = await service.add_from_file(
            db, storage, llm, org_id=ctx.org_id, document_id=body.document_id
        )
    else:
        job = await service.save_search_result(
            db, provider, org_id=ctx.org_id, external_id=body.external_id
        )
    return _out(job)


@router.get(
    "/search",
    response_model=UnifiedJobSearchResponse,
    responses=problem_responses(Unauthorized, ValidationFailed, UpstreamUnavailable),
)
async def search_jobs(
    ctx: Annotated[OrgContext, Depends(get_org_context)],  # authenticated users only
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[JobProvider, Depends(get_job_provider)],
    query: Annotated[str | None, Query(max_length=200)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    contract_type: Annotated[str | None, Query(max_length=50)] = None,
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> UnifiedJobSearchResponse:
    return await service.search(
        db,
        provider,
        query=query,
        department=department,
        contract_type=contract_type,
        page=page,
        limit=limit,
    )


@router.get("", response_model=list[JobOut], responses=problem_responses(Unauthorized))
async def list_jobs(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobOut]:
    jobs = await service.list_jobs(db, org_id=ctx.org_id, limit=limit, offset=offset)
    return [_out(j) for j in jobs]


@router.get(
    "/{job_id}",
    response_model=JobOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_job(
    job_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    return _out(await service.get_job(db, org_id=ctx.org_id, job_id=job_id))
