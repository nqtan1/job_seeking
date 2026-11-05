"""HTTP only: parse, call the service, map to a response schema (ADR 0031)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings, get_settings
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.errors import (
    Conflict,
    NotFound,
    Unauthorized,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.ratelimit import limit_ai, rate_limit
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.agents.deps import require_enabled
from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import runs as flow_runs
from recruitai.modules.agents.flows import schedules, starters
from recruitai.modules.agents.flows import service as flows
from recruitai.modules.agents.flows.models import (
    Flow,
    FlowRun,
    FlowSchedule,
    FlowVersion,
)
from recruitai.modules.agents.flows.schemas import (
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

router = APIRouter(
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


@router.post(
    "/flows",
    status_code=201,
    response_model=FlowDetail,
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def create_flow(body: FlowCreate, ctx: Ctx, db: Db) -> FlowDetail:
    f, v = await flows.create_flow(db, org_id=ctx.org_id, data=body)
    return await _flow_detail(db, ctx, f, v)


@router.post(
    "/flows/starters/job-hunter",
    status_code=201,
    response_model=FlowDetail,
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def install_job_hunter(ctx: Ctx, db: Db) -> FlowDetail:
    """The ready-made job hunter (search sentence -> new offers -> one prepared run per offer).
    Asking again returns the one that exists."""
    f, v = await starters.install_job_hunter(db, org_id=ctx.org_id)
    return await _flow_detail(db, ctx, f, v)


@router.get(
    "/flows", response_model=list[FlowOut], responses=problem_responses(Unauthorized)
)
async def list_flows(ctx: Ctx, db: Db) -> list[FlowOut]:
    items, versions = await flows.list_with_versions(db, org_id=ctx.org_id)
    return [_flow_out(f, versions[f.id]) for f in items if f.id in versions]


@router.post(
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


@router.post(
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


@router.get(
    "/flows/{flow_id}",
    response_model=FlowDetail,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_flow(flow_id: UUID, ctx: Ctx, db: Db) -> FlowDetail:
    f, v = await flows.get_detail(db, org_id=ctx.org_id, flow_id=flow_id)
    return await _flow_detail(db, ctx, f, v)


@router.patch(
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


@router.delete(
    "/flows/{flow_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def archive_flow(flow_id: UUID, ctx: Ctx, db: Db) -> Response:
    await flows.archive(db, org_id=ctx.org_id, flow_id=flow_id)
    return Response(status_code=204)


@router.get(
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


@router.post(
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


@router.post(
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
    run, created = await flow_runs.start_run(
        db, org_id=ctx.org_id, user_id=ctx.user_id, flow_id=flow_id, data=body,
        idempotency_key=idempotency_key,
    )  # fmt: skip
    if not created:
        response.status_code = 200
    return _run_summary(run)


@router.get(
    "/flows/{flow_id}/runs",
    response_model=list[RunSummary],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_runs(
    flow_id: UUID, ctx: Ctx, db: Db, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> list[RunSummary]:
    rows = await flow_runs.list_runs(
        db, org_id=ctx.org_id, flow_id=flow_id, limit=limit
    )
    return [_run_summary(r) for r in rows]


@router.get(
    "/flow-runs/{run_id}",
    response_model=RunOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_run(run_id: UUID, ctx: Ctx, db: Db) -> RunOut:
    run, steps, handoffs = await flow_runs.run_detail(
        db, org_id=ctx.org_id, run_id=run_id
    )
    return RunOut(
        **_run_summary(run).model_dump(),
        inputs=run.inputs,
        job_id=run.job_id,
        result=run.result,
        started_at=run.started_at,
        steps=[StepOut.model_validate(s, from_attributes=True) for s in steps],
        handoffs=[HandoffOut.model_validate(h, from_attributes=True) for h in handoffs],
    )


@router.post(
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
        await flow_runs.resume_run(
            db,
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            run_id=run_id,
            stale_after=flow_runs.stale_after(settings),
        )
    )


@router.post(
    "/flow-runs/{run_id}/cancel",
    response_model=RunSummary,
    responses=problem_responses(Unauthorized, NotFound, Conflict),
)
async def cancel_run(run_id: UUID, ctx: Ctx, db: Db) -> RunSummary:
    return _run_summary(
        await flow_runs.cancel_run(db, org_id=ctx.org_id, run_id=run_id)
    )


@router.get(
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
    rows = await flow_runs.list_org_runs(
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


@router.post(
    "/flow-runs/{run_id}/rerun",
    status_code=202,
    response_model=RunSummary,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(Unauthorized, NotFound, Conflict, ValidationFailed),
)
async def rerun(run_id: UUID, ctx: Ctx, db: Db) -> RunSummary:
    """Run again: a new run of the flow's current version with the same inputs."""
    return _run_summary(
        await flow_runs.rerun(db, org_id=ctx.org_id, user_id=ctx.user_id, run_id=run_id)
    )


def _schedule_out(s: FlowSchedule) -> ScheduleOut:
    return ScheduleOut.model_validate(s, from_attributes=True)


@router.get(
    "/flows/{flow_id}/schedules",
    response_model=list[ScheduleOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_schedules(flow_id: UUID, ctx: Ctx, db: Db) -> list[ScheduleOut]:
    rows = await schedules.list_schedules(db, org_id=ctx.org_id, flow_id=flow_id)
    return [_schedule_out(s) for s in rows]


@router.post(
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


@router.patch(
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


@router.delete(
    "/schedules/{schedule_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def delete_schedule(schedule_id: UUID, ctx: Ctx, db: Db) -> Response:
    await schedules.delete_schedule(db, org_id=ctx.org_id, schedule_id=schedule_id)
    return Response(status_code=204)
