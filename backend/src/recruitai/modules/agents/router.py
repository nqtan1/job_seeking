"""HTTP only: parse, call the service, map to a response schema (ADR 0031)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import LLMGateway
from recruitai.config import Settings, get_settings
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
from recruitai.core.ratelimit import limit_ai, rate_limit
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.agents import flows, schedules, service
from recruitai.modules.agents import graph as g
from recruitai.modules.agents.flow_schemas import (
    FlowCreate,
    FlowDetail,
    FlowOut,
    FlowPatch,
    FlowVersionCreate,
    FlowVersionOut,
    HandoffOut,
    IssueOut,
    PreviewIn,
    PreviewOut,
    PreviewValue,
    RunIn,
    RunListItem,
    RunOut,
    RunSummary,
    ScheduleIn,
    ScheduleOut,
    SchedulePatch,
    StepOut,
    ValidateIn,
    ValidateOut,
)
from recruitai.modules.agents.models import (
    Agent,
    AgentVersion,
    Flow,
    FlowRun,
    FlowSchedule,
    FlowVersion,
)
from recruitai.modules.agents.schemas import (
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


def require_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Off means the feature does not exist: a plain 404, so nothing leaks about it."""
    if not settings.helpers_enabled:
        raise NotFound("Not found.")


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


# flows and runs

flow_router = APIRouter(
    prefix="/api/v1", tags=["flows"], dependencies=[Depends(require_enabled)]
)
limit_preview = rate_limit(
    "flow_preview", limit=120
)  # no model call, but it renders on every edit
Ctx = Annotated[OrgContext, Depends(get_org_context)]
Db = Annotated[AsyncSession, Depends(get_db)]


def _issue(i: g.Issue) -> IssueOut:
    return IssueOut(
        code=i.code,
        message=i.message,
        node_id=i.node_id,
        edge_id=i.edge_id,
        severity=i.severity,
    )


def _flow_out(f: Flow, v: FlowVersion) -> FlowOut:
    return FlowOut(
        id=f.id,
        name=f.name,
        description=f.description,
        current_version=f.current_version,
        archived=f.archived_at is not None,
        max_ai_calls=flows.ai_calls(flows.graph_of(v)),
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


async def _flow_detail(
    db: AsyncSession, ctx: OrgContext, f: Flow, v: FlowVersion
) -> FlowDetail:
    graph = flows.graph_of(v)
    issues = await flows.check(db, org_id=ctx.org_id, graph=graph, flow_id=f.id)
    return FlowDetail(
        **_flow_out(f, v).model_dump(), graph=graph, issues=[_issue(i) for i in issues]
    )


def _run_summary(r: FlowRun) -> RunSummary:
    return RunSummary.model_validate(r, from_attributes=True)


@flow_router.post(
    "/flows",
    status_code=201,
    response_model=FlowDetail,
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def create_flow(body: FlowCreate, ctx: Ctx, db: Db) -> FlowDetail:
    f, v = await flows.create_flow(db, org_id=ctx.org_id, data=body)
    return await _flow_detail(db, ctx, f, v)


@flow_router.get(
    "/flows", response_model=list[FlowOut], responses=problem_responses(Unauthorized)
)
async def list_flows(ctx: Ctx, db: Db) -> list[FlowOut]:
    items, versions = await flows.list_with_versions(db, org_id=ctx.org_id)
    return [_flow_out(f, versions[f.id]) for f in items if f.id in versions]


@flow_router.post(
    "/flows/validate",
    response_model=ValidateOut,
    responses=problem_responses(Unauthorized),
)
async def validate_graph(body: ValidateIn, ctx: Ctx, db: Db) -> ValidateOut:
    """Checks a draft graph without saving it: the editor's validation panel."""
    issues = await flows.check(db, org_id=ctx.org_id, graph=body.graph)
    return ValidateOut(
        issues=[_issue(i) for i in issues],
        max_ai_calls=flows.ai_calls(body.graph),
        ok=not any(i.severity == "error" for i in issues),
    )


@flow_router.post(
    "/flows/preview-handoff",
    response_model=PreviewOut,
    dependencies=[Depends(limit_preview)],
    responses=problem_responses(Unauthorized),
)
async def preview_handoff(body: PreviewIn, ctx: Ctx) -> PreviewOut:
    """What the next step would receive: the same function the engine uses, never a copy of it."""
    values, truncated = g.render_map(body.map, body.outputs)
    return PreviewOut(
        values={k: PreviewValue(text=v, chars=len(v)) for k, v in values.items()},
        truncated=truncated,
    )


@flow_router.get(
    "/flows/{flow_id}",
    response_model=FlowDetail,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_flow(flow_id: UUID, ctx: Ctx, db: Db) -> FlowDetail:
    f, v = await flows.get_detail(db, org_id=ctx.org_id, flow_id=flow_id)
    return await _flow_detail(db, ctx, f, v)


@flow_router.patch(
    "/flows/{flow_id}",
    response_model=FlowOut,
    responses=problem_responses(Unauthorized, NotFound, Conflict),
)
async def patch_flow(flow_id: UUID, body: FlowPatch, ctx: Ctx, db: Db) -> FlowOut:
    f = await flows.patch_flow(
        db,
        org_id=ctx.org_id,
        flow_id=flow_id,
        name=body.name,
        description=body.description,
    )
    _, v = await flows.get_detail(db, org_id=ctx.org_id, flow_id=flow_id)
    return _flow_out(f, v)


@flow_router.delete(
    "/flows/{flow_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def archive_flow(flow_id: UUID, ctx: Ctx, db: Db) -> Response:
    await flows.archive(db, org_id=ctx.org_id, flow_id=flow_id)
    return Response(status_code=204)


@flow_router.get(
    "/flows/{flow_id}/versions",
    response_model=list[FlowVersionOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_flow_versions(flow_id: UUID, ctx: Ctx, db: Db) -> list[FlowVersionOut]:
    rows = await flows.list_versions(db, org_id=ctx.org_id, flow_id=flow_id)
    return [_flow_version_out(v) for v in rows]


def _flow_version_out(v: FlowVersion) -> FlowVersionOut:
    return FlowVersionOut(
        id=v.id, flow_id=v.flow_id, version=v.version, graph=flows.graph_of(v),
        note=v.note, created_at=v.created_at,
    )  # fmt: skip


@flow_router.post(
    "/flows/{flow_id}/versions",
    status_code=201,
    response_model=FlowVersionOut,
    responses=problem_responses(Unauthorized, NotFound, Conflict, ValidationFailed),
)
async def add_flow_version(
    flow_id: UUID, body: FlowVersionCreate, ctx: Ctx, db: Db
) -> FlowVersionOut:
    """409 when ``based_on`` is not the current version."""
    return _flow_version_out(
        await flows.add_version(db, org_id=ctx.org_id, flow_id=flow_id, data=body)
    )


@flow_router.post(
    "/flows/{flow_id}/runs",
    status_code=202,
    response_model=RunSummary,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses={
        **problem_responses(Unauthorized, NotFound, Conflict, ValidationFailed),
        200: {
            "model": RunSummary,
            "description": "The same Idempotency-Key was seen: the first run.",
        },
    },
)
async def start_run(
    flow_id: UUID,
    body: RunIn,
    ctx: Ctx,
    db: Db,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> RunSummary:
    """Queues a run (202). The same Idempotency-Key returns the first run (200) instead of a new one."""
    run, created = await flows.start_run(
        db, org_id=ctx.org_id, user_id=ctx.user_id, flow_id=flow_id, data=body,
        idempotency_key=idempotency_key,
    )  # fmt: skip
    if not created:
        response.status_code = 200
    return _run_summary(run)


@flow_router.get(
    "/flows/{flow_id}/runs",
    response_model=list[RunSummary],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_runs(
    flow_id: UUID, ctx: Ctx, db: Db, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> list[RunSummary]:
    rows = await flows.list_runs(db, org_id=ctx.org_id, flow_id=flow_id, limit=limit)
    return [_run_summary(r) for r in rows]


@flow_router.get(
    "/flow-runs/{run_id}",
    response_model=RunOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_run(run_id: UUID, ctx: Ctx, db: Db) -> RunOut:
    run, steps, handoffs = await flows.run_detail(db, org_id=ctx.org_id, run_id=run_id)
    return RunOut(
        **_run_summary(run).model_dump(),
        inputs=run.inputs,
        job_id=run.job_id,
        result=run.result,
        started_at=run.started_at,
        steps=[StepOut.model_validate(s, from_attributes=True) for s in steps],
        handoffs=[HandoffOut.model_validate(h, from_attributes=True) for h in handoffs],
    )


@flow_router.post(
    "/flow-runs/{run_id}/resume",
    status_code=202,
    response_model=RunSummary,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(Unauthorized, NotFound, Conflict),
)
async def resume_run(
    run_id: UUID,
    ctx: Ctx,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunSummary:
    """Runs only the failed or interrupted steps again; finished steps keep their output."""
    return _run_summary(
        await flows.resume_run(
            db,
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            run_id=run_id,
            stale_after=flows.stale_after(settings),
        )
    )


@flow_router.post(
    "/flow-runs/{run_id}/cancel",
    response_model=RunSummary,
    responses=problem_responses(Unauthorized, NotFound, Conflict),
)
async def cancel_run(run_id: UUID, ctx: Ctx, db: Db) -> RunSummary:
    return _run_summary(await flows.cancel_run(db, org_id=ctx.org_id, run_id=run_id))


@flow_router.get(
    "/flow-runs",
    response_model=list[RunListItem],
    responses=problem_responses(Unauthorized),
)
async def list_all_runs(
    ctx: Ctx,
    db: Db,
    status: Annotated[
        str | None, Query(pattern="^(queued|running|waiting|done|failed|cancelled)$")
    ] = None,
    flow_id: UUID | None = None,
    before_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
) -> list[RunListItem]:
    """Every run of the account, newest first. Page with ``before_id`` = the id of the last row."""
    rows = await flows.list_org_runs(
        db,
        org_id=ctx.org_id,
        status=status,
        flow_id=flow_id,
        before_id=before_id,
        limit=limit,
    )
    return [
        RunListItem(**_run_summary(r).model_dump(), flow_name=name) for r, name in rows
    ]


@flow_router.post(
    "/flow-runs/{run_id}/rerun",
    status_code=202,
    response_model=RunSummary,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(Unauthorized, NotFound, Conflict, ValidationFailed),
)
async def rerun(run_id: UUID, ctx: Ctx, db: Db) -> RunSummary:
    """Run again: a new run of the flow's current version with the same inputs."""
    return _run_summary(
        await flows.rerun(db, org_id=ctx.org_id, user_id=ctx.user_id, run_id=run_id)
    )


def _schedule_out(s: FlowSchedule) -> ScheduleOut:
    return ScheduleOut.model_validate(s, from_attributes=True)


@flow_router.get(
    "/flows/{flow_id}/schedules",
    response_model=list[ScheduleOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_schedules(flow_id: UUID, ctx: Ctx, db: Db) -> list[ScheduleOut]:
    rows = await schedules.list_schedules(db, org_id=ctx.org_id, flow_id=flow_id)
    return [_schedule_out(s) for s in rows]


@flow_router.post(
    "/flows/{flow_id}/schedules",
    status_code=201,
    response_model=ScheduleOut,
    responses=problem_responses(Unauthorized, NotFound, Conflict, ValidationFailed),
)
async def create_schedule(
    flow_id: UUID, body: ScheduleIn, ctx: Ctx, db: Db
) -> ScheduleOut:
    """Run this flow by itself (hourly, daily or weekly) with the inputs given here."""
    return _schedule_out(
        await schedules.create_schedule(
            db, org_id=ctx.org_id, user_id=ctx.user_id, flow_id=flow_id, data=body
        )
    )


@flow_router.patch(
    "/schedules/{schedule_id}",
    response_model=ScheduleOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def patch_schedule(
    schedule_id: UUID, body: SchedulePatch, ctx: Ctx, db: Db
) -> ScheduleOut:
    """Pause or resume. Resuming clears a pause and starts counting from now."""
    return _schedule_out(
        await schedules.set_enabled(
            db, org_id=ctx.org_id, schedule_id=schedule_id, enabled=body.enabled
        )
    )


@flow_router.delete(
    "/schedules/{schedule_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def delete_schedule(schedule_id: UUID, ctx: Ctx, db: Db) -> Response:
    await schedules.delete_schedule(db, org_id=ctx.org_id, schedule_id=schedule_id)
    return Response(status_code=204)
