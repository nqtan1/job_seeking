"""Runs of a flow: start, fan out, resume, cancel, sweeps (ADR 0031). The engine (``engine.py``)
does the actual work in the worker."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import usage
from recruitai.config import Settings
from recruitai.core.errors import Conflict, NotFound, ValidationFailed
from recruitai.modules.agents.blocks.catalogue import BLOCKS
from recruitai.modules.agents.blocks.errors import DailyLimit
from recruitai.modules.agents.flows import engine
from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import repository as repo
from recruitai.modules.agents.flows.models import (
    Flow,
    FlowRun,
    FlowRunHandoff,
    FlowRunStep,
    FlowVersion,
)
from recruitai.modules.agents.flows.schemas import RunIn
from recruitai.modules.agents.flows.service import (
    ai_calls,
    check,
    get_detail,
    get_flow,
    graph_of,
)
from recruitai.modules.jobs import service as jobs

MAX_ACTIVE_RUNS = 2  # waiting runs do not count (accepted: they hold no worker)
MAX_ACTIVE_CHILDREN = 10  # runs started by for_each steps, all together
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


# runs


def _check_inputs(graph: g.Graph, inputs: dict[str, str]) -> None:
    node = next(n for n in graph.nodes if isinstance(n, g.InputNode))
    declared = {f.name for f in node.fields}
    if extra := set(inputs) - declared:
        raise ValidationFailed(f"Unknown input: {min(extra)}.")
    for f in node.fields:
        if f.required and not inputs.get(f.name, "").strip():
            raise ValidationFailed(f"“{f.label}” is required.")


def _needs_job(graph: g.Graph, agents: dict[UUID, g.AgentInfo]) -> bool:
    return any(
        {"job", "fit"} & set(a.spec.context_sources) for a in agents.values()
    ) or any(
        isinstance(n, g.ToolNode) and BLOCKS[n.tool].needs_job for n in graph.nodes
    )


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
    issues = await check(db, org_id=org_id, graph=graph, agents=agents, flow_id=flow_id)
    if any(i.severity == "error" for i in issues):
        raise ValidationFailed("This flow has problems. Fix them before running it.")
    _check_inputs(graph, data.inputs)
    if _needs_job(graph, agents) and data.job_id is None:
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
    parent_run_id: UUID | None = None,
    lock: str | None = None,
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
    child = (
        parent_run_id is not None
    )  # capped by its parent's step, not by the live-run limit
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
    if not child and await repo.count_active_runs(db, org_id=org_id) >= MAX_ACTIVE_RUNS:
        raise OrgBusy("Two flows are already running. Wait for one to finish.")
    if (
        child
        and await repo.count_active_children(db, org_id=org_id) >= MAX_ACTIVE_CHILDREN
    ):
        raise OrgBusy(
            "Too many started runs are still going. Resume this step shortly."
        )

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
                "trigger": "flow" if child else "schedule" if schedule_id else "manual",
                "schedule_id": schedule_id,
                "parent_run_id": parent_run_id,
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
    await _enqueue(db, org_id=org_id, user_id=user_id, run_id=run.id, lock=lock)
    await db.commit()
    return run, True


def _fan_key(parent_id: UUID, flow_id: UUID, inputs: dict[str, str]) -> str:
    """Same parent, flow and item = same run, however often a resumed step asks."""
    raw = f"{parent_id}|{flow_id}|{json.dumps(inputs, sort_keys=True)}"
    return "fan:" + hashlib.sha256(raw.encode()).hexdigest()[:48]


CHILD_SLOTS = 2  # runs started by for_each that one user's worker slots serve at a time


async def fan_out(
    db: AsyncSession,
    *,
    parent: FlowRun,
    flow_id: UUID,
    items: list[dict[str, str]],
    daily_quota: int,
) -> list[FlowRun]:
    """One run of ``flow_id`` per item (ADR 0034/0035). An item's ``job_id`` is the started run's
    job; its other keys fill the target's Start step by name (unknown keys are ignored). The runs
    are queued two at a time per user, and only as many as the user's remaining daily AI calls
    pay for: the rest raises ``DailyLimit`` after the first are started, so Resume starts only the
    missing ones (same items = same runs). A repeated call returns the runs already started."""
    assert parent.user_id is not None
    _, version = await get_detail(db, org_id=parent.org_id, flow_id=flow_id)
    graph = graph_of(version)
    start = next(n for n in graph.nodes if isinstance(n, g.InputNode))
    wanted = {f.name for f in start.fields}
    prepared: list[tuple[dict[str, str], UUID | None]] = []
    for item in items:
        inputs = {k: v for k, v in item.items() if k in wanted}
        _check_inputs(graph, inputs)
        try:
            job = UUID(item["job_id"]) if item.get("job_id") else None
        except ValueError as exc:
            raise ValidationFailed("An item has an invalid job.") from exc
        if job is not None:
            await jobs.get_job(db, org_id=parent.org_id, job_id=job)  # 404 across orgs
        prepared.append(
            (inputs, job)
        )  # every item is checked before the first run starts
    per_run = ai_calls(graph)
    used = await usage.count_calls_today(db, user_id=parent.user_id)
    room = max(daily_quota - used, 0)
    affordable = len(prepared) if per_run == 0 else room // per_run
    runs: list[FlowRun] = []
    for i, (inputs, job) in enumerate(prepared[:affordable]):
        status = await repo.run_status(db, org_id=parent.org_id, run_id=parent.id)
        if status in ("cancelled", "failed"):
            return runs  # stopped meanwhile: start nothing more
        run, _ = await start_run(
            db,
            org_id=parent.org_id,
            user_id=parent.user_id,
            flow_id=flow_id,
            data=RunIn(inputs=inputs, job_id=job),
            idempotency_key=_fan_key(
                parent.id, flow_id, {**inputs, "job_id": str(job)}
            ),
            parent_run_id=parent.id,
            lock=f"children:{parent.user_id}:{i % CHILD_SLOTS}",
        )
        runs.append(run)
    if affordable < len(prepared):
        raise DailyLimit()
    return runs


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
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    run_id: UUID,
    lock: str | None = None,
) -> None:
    await engine.enqueue_run(
        db, org_id=org_id, user_id=user_id, run_id=run_id, lock=lock
    )


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
    seen = (
        run.updated_at
    )  # read now: the guard below must compare against what was judged
    stale = run.status == "running" and datetime.now(UTC) - seen > stale_after
    if run.status != "failed" and not stale:
        raise Conflict("Only a failed or stuck run can be resumed.")
    if not stale and await repo.count_active_runs(db, org_id=org_id) >= MAX_ACTIVE_RUNS:
        raise OrgBusy("Two flows are already running. Wait for one to finish.")
    await repo.reset_unfinished_steps(db, org_id=org_id, run_id=run_id)
    changed = await repo.set_run(
        db, org_id=org_id, run_id=run_id, only_if=("failed", "running"),
        seen_updated_at=seen, status="queued", error_code=None, finished_at=None, result=None,
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


async def sweep_old_runs(db: AsyncSession, *, cutoff: datetime) -> int:
    """Retention (ADR 0031 / 0014): run content is user content and does not live forever."""
    deleted = await repo.delete_runs_older_than(db, cutoff=cutoff)
    await db.commit()
    return deleted
