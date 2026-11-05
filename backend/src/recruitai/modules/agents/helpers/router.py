"""HTTP only: parse, call the service, map to a response schema (ADR 0031)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import LLMGateway
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.errors import (
    Conflict,
    NotFound,
    Unauthorized,
    UpstreamUnavailable,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.ratelimit import limit_ai
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.agents.deps import require_enabled
from recruitai.modules.agents.helpers import service
from recruitai.modules.agents.helpers.models import Agent, AgentVersion
from recruitai.modules.agents.helpers.schemas import (
    AgentCreate,
    AgentDetail,
    AgentOut,
    AgentPatch,
    AgentVersionOut,
    Avatar,
    TrialIn,
    TrialOut,
    VersionCreate,
)

router = APIRouter(
    prefix="/api/v1/agents", tags=["agents"], dependencies=[Depends(require_enabled)]
)


def _agent_out(a: Agent) -> AgentOut:
    return AgentOut(
        id=a.id,
        name=a.name,
        description=a.description,
        avatar=Avatar.model_validate(a.avatar),
        current_version=a.current_version,
        archived=a.archived_at is not None,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _version_out(v: AgentVersion) -> AgentVersionOut:
    return AgentVersionOut(
        id=v.id,
        agent_id=v.agent_id,
        version=v.version,
        spec=service.spec_of(v),
        note=v.note,
        created_at=v.created_at,
    )


def _detail(a: Agent, v: AgentVersion) -> AgentDetail:
    return AgentDetail(
        **_agent_out(a).model_dump(), version_id=v.id, spec=service.spec_of(v)
    )


@router.post(
    "",
    status_code=201,
    response_model=AgentDetail,
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def create_agent(
    body: AgentCreate,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDetail:
    return _detail(*await service.create_agent(db, org_id=ctx.org_id, data=body))


@router.get(
    "", response_model=list[AgentOut], responses=problem_responses(Unauthorized)
)
async def list_agents(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentOut]:
    return [_agent_out(a) for a in await service.list_agents(db, org_id=ctx.org_id)]


@router.get(
    "/{agent_id}",
    response_model=AgentDetail,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_agent(
    agent_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentDetail:
    return _detail(*await service.get_detail(db, org_id=ctx.org_id, agent_id=agent_id))


@router.patch(
    "/{agent_id}",
    response_model=AgentOut,
    responses=problem_responses(Unauthorized, NotFound, Conflict),
)
async def patch_agent(
    agent_id: UUID,
    body: AgentPatch,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentOut:
    return _agent_out(
        await service.patch_agent(db, org_id=ctx.org_id, agent_id=agent_id, data=body)
    )


@router.delete(
    "/{agent_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def archive_agent(
    agent_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Archives (flows that pin it keep working); nothing is destroyed."""
    await service.archive(db, org_id=ctx.org_id, agent_id=agent_id)
    return Response(status_code=204)


@router.get(
    "/{agent_id}/versions",
    response_model=list[AgentVersionOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_versions(
    agent_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentVersionOut]:
    rows = await service.list_versions(db, org_id=ctx.org_id, agent_id=agent_id)
    return [_version_out(v) for v in rows]


@router.post(
    "/{agent_id}/versions",
    status_code=201,
    response_model=AgentVersionOut,
    responses=problem_responses(Unauthorized, NotFound, Conflict, ValidationFailed),
)
async def add_version(
    agent_id: UUID,
    body: VersionCreate,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentVersionOut:
    """409 when ``based_on`` is not the current version: a stale editor never overwrites."""
    return _version_out(
        await service.add_version(db, org_id=ctx.org_id, agent_id=agent_id, data=body)
    )


@router.post(
    "/{agent_id}/trial",
    response_model=TrialOut,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, Conflict, ValidationFailed, UpstreamUnavailable
    ),
)
async def trial(
    agent_id: UUID,
    body: TrialIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> TrialOut:
    """Runs a draft once (Try-it panel). Costs one AI use; nothing is stored."""
    outcome = await service.try_it(
        db,
        llm,
        org_id=ctx.org_id,
        agent_id=agent_id,
        spec=body.spec,
        inputs=body.inputs,
        job_id=body.job_id,
    )
    return TrialOut(
        result=outcome.result, model=outcome.model, latency_ms=outcome.latency_ms
    )
