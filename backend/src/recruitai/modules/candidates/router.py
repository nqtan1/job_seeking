"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated

from fastapi import APIRouter, Depends
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
from recruitai.modules.candidates import service
from recruitai.modules.candidates.models import CandidateProfile
from recruitai.modules.candidates.schemas import (
    CVInformation,
    ExtractRequest,
    ProfileOut,
    ProfileUpdate,
)

router = APIRouter(prefix="/api/v1/profile", tags=["candidates"])


def _out(profile: CandidateProfile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        document_id=profile.document_id,
        data=CVInformation.model_validate(profile.data),
        schema_version=profile.schema_version,
        updated_at=profile.updated_at,
    )


@router.post(
    "/extract",
    response_model=ProfileOut,
    # App Check on the one AI-cost endpoint here (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def extract_profile(
    body: ExtractRequest,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> ProfileOut:
    profile = await service.extract(
        db, storage, llm, org_id=ctx.org_id, document_id=body.document_id
    )
    return _out(profile)


@router.get(
    "", response_model=ProfileOut, responses=problem_responses(Unauthorized, NotFound)
)
async def read_profile(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileOut:
    return _out(await service.get_profile(db, org_id=ctx.org_id))


@router.patch(
    "",
    response_model=ProfileOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def update_profile(
    body: ProfileUpdate,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileOut:
    return _out(await service.update_profile(db, org_id=ctx.org_id, changes=body))
