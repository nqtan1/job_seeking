"""Flows and runs: CRUD with immutable versions, validation, starting/resuming/cancelling a run
(ADR 0031). The engine (``engine.py``) does the actual work in the worker."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings
from recruitai.core.errors import Conflict, NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.modules.agents import engine, service
from recruitai.modules.agents import flow_repository as repo
from recruitai.modules.agents import graph as g
from recruitai.modules.agents import recipients_repository as recipients_repo
from recruitai.modules.agents.flow_schemas import FlowCreate, FlowVersionCreate, RunIn
from recruitai.modules.agents.models import (
    Flow,
    FlowRun,
    FlowRunHandoff,
    FlowRunStep,
    FlowVersion,
)
from recruitai.modules.jobs import service as jobs

MAX_FLOWS_PER_ORG = 20
MAX_FLOWS_EVER = 100  # archived ones count too: archiving is not a way around the cap
MAX_ACTIVE_RUNS = 2
WAKE_GRACE = timedelta(
    minutes=10
)  # a wake-up job this late is lost: the sweep fails the run


class OrgBusy(Conflict):
    """Too many live runs right now: transient, unlike an archived flow."""


def stale_after(settings: Settings) -> timedelta:
    """A model call may take ``ai_call_timeout_s`` and is retried once on an invalid answer, so a
    run silent for less than twice that (plus a margin) is still alive and cannot be resumed."""
    return timedelta(seconds=2 * settings.ai_call_timeout_s + 60)


def abandoned_after(settings: Settings) -> timedelta:
    """...and a run silent for twice that is dead: the sweep fails it so it can be resumed."""
    return max(timedelta(minutes=10), 2 * stale_after(settings))


RUN_TASK = engine.RUN_TASK
# Saving is allowed with open problems (work in progress); these make a graph unreadable.
UNSAVABLE = {"duplicate_node_id", "duplicate_edge_id"}


def graph_of(version: FlowVersion) -> g.Graph:
    return g.Graph.model_validate(version.graph)


def ai_calls(graph: g.Graph) -> int:
    """Model calls a run can make: one per helper, and one per web search."""
    return sum(
        isinstance(n, g.AgentNode)
        or (isinstance(n, g.ToolNode) and n.tool == "web_search")
        for n in graph.nodes
    )


async def check(
    db: AsyncSession,
    *,
    org_id: UUID,
    graph: g.Graph,
    agents: dict[UUID, g.AgentInfo] | None = None,
) -> list[g.Issue]:
    if agents is None:
        agents = await engine.load_agents(db, org_id=org_id, graph=graph)
    return g.validate(graph, agents)


def _refuse_unsavable(issues: list[g.Issue]) -> None:
    if bad := [i for i in issues if i.code in UNSAVABLE]:
        raise ValidationFailed(bad[0].message)


async def create_flow(
    db: AsyncSession, *, org_id: UUID, data: FlowCreate
) -> tuple[Flow, FlowVersion]:
    if await repo.count_flows(db, org_id=org_id) >= MAX_FLOWS_PER_ORG:
        raise ValidationFailed(f"You can have at most {MAX_FLOWS_PER_ORG} flows.")
    if (
        await repo.count_flows(db, org_id=org_id, include_archived=True)
        >= MAX_FLOWS_EVER
    ):
        raise ValidationFailed("You have reached the limit of flows you can create.")
    _refuse_unsavable(await check(db, org_id=org_id, graph=data.graph))
    flow = await repo.create_flow(
        db,
        org_id=org_id,
        values={
            "name": data.name.strip(),
            "description": data.description.strip(),
            "current_version": 1,
        },
    )
    version = await repo.add_flow_version(
        db,
        org_id=org_id,
        flow_id=flow.id,
        values=_version_values(data.graph, data.note, 1),
    )
    await db.commit()
    return flow, version


def _version_values(graph: g.Graph, note: str, version: int) -> dict[str, Any]:
    return {
        "version": version,
        "graph": graph.model_dump(mode="json", by_alias=True),
        "schema_version": g.SCHEMA_VERSION,
        "note": note,
    }


async def get_flow(db: AsyncSession, *, org_id: UUID, flow_id: UUID) -> Flow:
    flow = await repo.get_flow(db, org_id=org_id, flow_id=flow_id)
    if flow is None:
        raise NotFound("Flow not found.")
    return flow


async def get_detail(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> tuple[Flow, FlowVersion]:
    flow = await get_flow(db, org_id=org_id, flow_id=flow_id)
    version = await repo.get_flow_version(
        db, org_id=org_id, flow_id=flow_id, version=flow.current_version
    )
    if version is None:
        raise NotFound("Flow not found.")
    return flow, version


async def list_flows(db: AsyncSession, *, org_id: UUID) -> list[Flow]:
    return await repo.list_flows(db, org_id=org_id)


async def list_with_versions(
    db: AsyncSession, *, org_id: UUID
) -> tuple[list[Flow], dict[UUID, FlowVersion]]:
    return (
        await repo.list_flows(db, org_id=org_id),
        await repo.current_versions(db, org_id=org_id),
    )


async def list_versions(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> list[FlowVersion]:
    await get_flow(db, org_id=org_id, flow_id=flow_id)
    return await repo.list_flow_versions(db, org_id=org_id, flow_id=flow_id)


async def patch_flow(
    db: AsyncSession,
    *,
    org_id: UUID,
    flow_id: UUID,
    name: str | None,
    description: str | None,
) -> Flow:
    flow = await get_flow(db, org_id=org_id, flow_id=flow_id)
    if flow.archived_at is not None:
        raise Conflict("This flow is archived.")
    values: dict[str, Any] = {}
    if name is not None:
        if not name.strip():
            raise ValidationFailed("The name is empty.")
        values["name"] = name.strip()
    if description is not None:
        values["description"] = description.strip()
    if values:
        await service.update_row(db, Flow, org_id=org_id, id=flow_id, values=values)
        await db.commit()
        await db.refresh(flow)
    return flow


async def add_version(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID, data: FlowVersionCreate
) -> FlowVersion:
    flow = await get_flow(db, org_id=org_id, flow_id=flow_id)
    _refuse_unsavable(await check(db, org_id=org_id, graph=data.graph))
    number = await service.claim_next_version(
        db, Flow, flow, org_id=org_id, based_on=data.based_on, noun="flow"
    )
    version = await repo.add_flow_version(
        db,
        org_id=org_id,
        flow_id=flow_id,
        values=_version_values(data.graph, data.note, number),
    )
    await db.commit()
    return version


async def archive(db: AsyncSession, *, org_id: UUID, flow_id: UUID) -> None:
    await get_flow(db, org_id=org_id, flow_id=flow_id)
    await service.archive_row(db, Flow, org_id=org_id, id=flow_id)
    await db.commit()


# runs


def _check_inputs(graph: g.Graph, inputs: dict[str, str]) -> None:
    node = next(n for n in graph.nodes if isinstance(n, g.InputNode))
    declared = {f.name for f in node.fields}
    if extra := set(inputs) - declared:
        raise ValidationFailed(f"Unknown input: {min(extra)}.")
    for f in node.fields:
        if f.required and not inputs.get(f.name, "").strip():
            raise ValidationFailed(f"“{f.label}” is required.")


async def prepare_run(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID, data: RunIn
) -> tuple[Flow, FlowVersion, g.Graph]:
    """Everything that must be true before a run is queued or a schedule is saved: the flow is
    live and valid, the inputs fit its Start step, a job is given when a helper reads one."""
    flow, version = await get_detail(db, org_id=org_id, flow_id=flow_id)
    if flow.archived_at is not None:
        raise Conflict("This flow is archived.")
    graph = graph_of(version)
    agents = await engine.load_agents(db, org_id=org_id, graph=graph)
    issues = await check(db, org_id=org_id, graph=graph, agents=agents)
    if any(i.severity == "error" for i in issues):
        raise ValidationFailed("This flow has problems. Fix them before running it.")
    _check_inputs(graph, data.inputs)
    needs_job = any(
        {"job", "fit"} & set(a.spec.context_sources) for a in agents.values()
    ) or any(isinstance(n, g.ToolNode) and n.tool == "job_lookup" for n in graph.nodes)
    if needs_job and data.job_id is None:
        raise ValidationFailed("This flow needs a job: pick one.")
    if data.job_id is not None:
        await jobs.get_job(db, org_id=org_id, job_id=data.job_id)  # 404 across orgs
    return flow, version, graph


async def start_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    flow_id: UUID,
    data: RunIn,
    idempotency_key: str | None,
    schedule_id: UUID | None = None,
) -> tuple[FlowRun, bool]:
    """Queue a run. Returns ``(run, created)``: a repeated idempotency key returns the first run."""
    idempotency_key = (idempotency_key or "").strip() or None
    if idempotency_key:
        if len(idempotency_key) > 80:
            raise ValidationFailed("The idempotency key is too long.")
        if existing := await repo.find_run_by_key(
            db, org_id=org_id, key=idempotency_key
        ):
            return _same_request(existing, flow_id, data), False
    _, version, graph = await prepare_run(db, org_id=org_id, flow_id=flow_id, data=data)
    await repo.lock_org_runs(db, org_id=org_id)  # count and insert as one step
    if (
        idempotency_key
        and (  # a twin request may have won while this one waited for the lock
            existing := await repo.find_run_by_key(
                db, org_id=org_id, key=idempotency_key
            )
        )
    ):
        return _same_request(existing, flow_id, data), False
    if await repo.count_active_runs(db, org_id=org_id) >= MAX_ACTIVE_RUNS:
        raise OrgBusy("Two flows are already running. Wait for one to finish.")

    try:
        run = await repo.create_run(
            db,
            org_id=org_id,
            values={
                "user_id": user_id,
                "flow_id": flow_id,
                "flow_version_id": version.id,
                "inputs": dict(data.inputs),
                "job_id": data.job_id,
                "idempotency_key": idempotency_key,
                "trigger": "schedule" if schedule_id else "manual",
                "schedule_id": schedule_id,
            },
        )
    except (
        IntegrityError
    ):  # two identical requests raced: the loser returns the winner's run
        await db.rollback()
        if idempotency_key and (
            existing := await repo.find_run_by_key(
                db, org_id=org_id, key=idempotency_key
            )
        ):
            return _same_request(existing, flow_id, data), False
        raise
    order = g.topological(graph)
    assert order is not None  # validated above
    await repo.create_steps(db, org_id=org_id, run_id=run.id, node_ids=order)
    await _enqueue(db, org_id=org_id, user_id=user_id, run_id=run.id)
    await db.commit()
    return run, True


async def rerun(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, run_id: UUID
) -> FlowRun:
    """ "Run again": a new run of the flow's current version with the same inputs and job."""
    old = await get_run(db, org_id=org_id, run_id=run_id)
    run, _ = await start_run(
        db,
        org_id=org_id,
        user_id=user_id,
        flow_id=old.flow_id,
        data=RunIn(inputs=dict(old.inputs), job_id=old.job_id),
        idempotency_key=None,
    )
    return run


async def list_org_runs(
    db: AsyncSession,
    *,
    org_id: UUID,
    status: str | None,
    flow_id: UUID | None,
    before_id: UUID | None,
    limit: int,
) -> list[tuple[FlowRun, str]]:
    return await repo.list_org_runs(
        db,
        org_id=org_id,
        status=status,
        flow_id=flow_id,
        before_id=before_id,
        limit=limit,
    )


def _same_request(run: FlowRun, flow_id: UUID, data: RunIn) -> FlowRun:
    """A key repeats the same request; the same key for a different one is a client bug."""
    if (
        run.flow_id != flow_id
        or run.inputs != dict(data.inputs)
        or run.job_id != data.job_id
    ):
        raise Conflict("This idempotency key was already used for a different request.")
    return run


async def _enqueue(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, run_id: UUID
) -> None:
    await engine.enqueue_run(db, org_id=org_id, user_id=user_id, run_id=run_id)


async def get_run(db: AsyncSession, *, org_id: UUID, run_id: UUID) -> FlowRun:
    run = await repo.get_run(db, org_id=org_id, run_id=run_id)
    if run is None:
        raise NotFound("Run not found.")
    return run


async def run_detail(
    db: AsyncSession, *, org_id: UUID, run_id: UUID
) -> tuple[FlowRun, list[FlowRunStep], list[FlowRunHandoff]]:
    run = await get_run(db, org_id=org_id, run_id=run_id)
    return (
        run,
        await repo.list_steps(db, org_id=org_id, run_id=run_id),
        await repo.list_handoffs(db, org_id=org_id, run_id=run_id),
    )


async def list_runs(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID, limit: int = 20
) -> list[FlowRun]:
    await get_flow(db, org_id=org_id, flow_id=flow_id)
    return await repo.list_runs(db, org_id=org_id, flow_id=flow_id, limit=limit)


async def resume_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    run_id: UUID,
    stale_after: timedelta,
) -> FlowRun:
    """Re-queue a failed run (or one silent for ``stale_after``): done steps keep their output,
    only the failed or interrupted ones run again. Never automatic: the user decides to spend."""
    await repo.lock_org_runs(db, org_id=org_id)
    run = await get_run(db, org_id=org_id, run_id=run_id)
    stale = run.status == "running" and datetime.now(UTC) - run.updated_at > stale_after
    if run.status != "failed" and not stale:
        raise Conflict("Only a failed or stuck run can be resumed.")
    if not stale and await repo.count_active_runs(db, org_id=org_id) >= MAX_ACTIVE_RUNS:
        raise OrgBusy("Two flows are already running. Wait for one to finish.")
    await repo.reset_unfinished_steps(db, org_id=org_id, run_id=run_id)
    changed = await repo.set_run(
        db, org_id=org_id, run_id=run_id, only_if=("failed", "running"),
        status="queued", error_code=None, finished_at=None, result=None,
    )  # fmt: skip
    if not changed:
        await db.rollback()
        raise Conflict("This run changed while resuming. Reload it.")
    await _enqueue(db, org_id=org_id, user_id=user_id, run_id=run_id)
    await db.commit()
    await db.refresh(run)
    return run


async def cancel_run(db: AsyncSession, *, org_id: UUID, run_id: UUID) -> FlowRun:
    run = await get_run(db, org_id=org_id, run_id=run_id)
    if not await repo.set_run(
        db, org_id=org_id, run_id=run_id, only_if=repo.LIVE,
        status="cancelled", wake_at=None, finished_at=func.now(),
    ):  # fmt: skip
        await db.rollback()
        raise Conflict("This run already ended.")
    await repo.fail_running_steps(db, org_id=org_id, run_id=run_id, code="cancelled")
    await db.commit()
    await db.refresh(run)
    return run


async def fail_stale_runs(
    db: AsyncSession, *, now: datetime, abandoned_after: timedelta
) -> int:
    """Backstop for a worker that died: a run that has not moved for a while is failed (and
    becomes resumable) instead of holding a slot forever."""
    cutoff = now - abandoned_after
    n = 0
    for org_id, run_id in await repo.stale_running(db, cutoff=cutoff):
        if await repo.fail_active_run(
            db, org_id=org_id, run_id=run_id, code="worker_stopped", older_than=cutoff
        ):
            n += 1
    for org_id, run_id in await repo.lost_waiting(db, cutoff=now - WAKE_GRACE):
        if await repo.fail_lost_waiting(
            db, org_id=org_id, run_id=run_id, cutoff=now - WAKE_GRACE
        ):
            n += 1
    await db.commit()
    return n


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, object]]]:
    flows, versions, runs, steps, handoffs = await repo.all_for_org(db, org_id=org_id)
    return {
        "flows": rows_as_dicts(flows),
        "flow_versions": rows_as_dicts(versions),
        "flow_runs": rows_as_dicts(runs),
        "flow_run_steps": rows_as_dicts(steps),
        "flow_run_handoffs": rows_as_dicts(handoffs),
        "flow_schedules": rows_as_dicts(
            await repo.schedules_for_org(db, org_id=org_id)
        ),
        # the link secrets are not data about the person: never in the export
        "email_recipients": [
            {
                k: v
                for k, v in row.items()
                if k not in ("confirm_hash", "unsubscribe_token")
            }
            for row in rows_as_dicts(
                await recipients_repo.all_for_org(db, org_id=org_id)
            )
        ],
    }


async def sweep_old_runs(db: AsyncSession, *, cutoff: datetime) -> int:
    """Retention (ADR 0031 / 0014): run content is user content and does not live forever."""
    deleted = await repo.delete_runs_older_than(db, cutoff=cutoff)
    await db.commit()
    return deleted
