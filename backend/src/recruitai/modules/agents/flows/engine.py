"""Runs a flow (ADR 0031). ``execute`` is idempotent and resumable: it recomputes where it is from
the stored step rows, so a repeated delivery, a resume after a failure, or a restart all do the
same thing. Every state change is committed before the next model call, so no transaction is held
open across it and a crash leaves an honest record.

Isolation: a step's input is built only from the ``map`` of its incoming, active edges. Steps are
keyed by node id, so the same helper used twice is two independent steps."""

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway
from recruitai.ai.prompts import helper
from recruitai.config import get_settings
from recruitai.core import inbox
from recruitai.core import tools as registry
from recruitai.core.errors import AppError
from recruitai.core.tasks import enqueue
from recruitai.modules.agents.blocks import tools
from recruitai.modules.agents.blocks.errors import ToolFailed
from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import repository as flow_repo
from recruitai.modules.agents.flows.models import FlowRun, FlowRunStep
from recruitai.modules.agents.helpers import repository, runner, service

logger = logging.getLogger(__name__)

RUN_TIMEOUT_S = 300.0
RUN_TASK = "agents:run_flow"  # registered by the worker (worker.py, namespace "agents")


class _Stop(Exception):
    """The run ended (failed or cancelled) or parked on a wait step: unwinds to ``execute``."""


async def enqueue_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    run_id: UUID,
    schedule_at: datetime | None = None,
    lock: str | None = None,
) -> None:
    await enqueue(
        db,
        task=RUN_TASK,
        org_id=org_id,
        kind="agents.run_flow",
        task_kwargs={
            "org_id": str(org_id),
            "user_id": str(user_id),
            "run_id": str(run_id),
        },
        schedule_at=schedule_at,
        lock=lock,
    )


async def _park(
    db: AsyncSession, run: FlowRun, step: FlowRunStep, node: g.ToolNode, value: str
) -> NoReturn:
    """Sleep without a worker or a transaction: the step and the run say "waiting until", and a
    job scheduled for that moment wakes the run (all in one commit)."""
    org_id, run_id, user_id = run.org_id, run.id, run.user_id
    if user_id is None:
        await _fail(db, run, step, "tool_failed")
    await flow_repo.lock_org_runs(db, org_id=org_id)
    if (
        await flow_repo.count_waiting_runs(db, org_id=org_id)
        >= flow_repo.MAX_WAITING_RUNS_PER_ORG
    ):
        await _fail(db, run, step, "too_many_waiting")
    assert node.minutes is not None  # validated with the node
    wake_at = datetime.now(UTC) + timedelta(minutes=node.minutes)
    await flow_repo.set_step(
        db,
        org_id=org_id,
        step_id=step.id,
        status="waiting",
        output={"value": value, "wake_at": wake_at.isoformat()},
        started_at=func.now(),
    )
    if not await flow_repo.set_run(
        db,
        org_id=org_id,
        run_id=run_id,
        only_if=("running",),
        status="waiting",
        wake_at=wake_at,
    ):
        await db.rollback()  # a cancel landed first: leave no waiting step behind
        raise _Stop
    await enqueue_run(
        db, org_id=org_id, user_id=user_id, run_id=run_id, schedule_at=wake_at
    )
    await db.commit()
    raise _Stop


async def load_agents(
    db: AsyncSession, *, org_id: UUID, graph: g.Graph
) -> dict[UUID, g.AgentInfo]:
    ids = [n.agent_version_id for n in graph.nodes if isinstance(n, g.AgentNode)]
    pairs = await repository.versions_by_ids(db, org_id=org_id, version_ids=ids)
    return {
        v.id: g.AgentInfo(spec=service.spec_of(v), agent_id=a.id, version=v.version)
        for v, a in pairs
    }


async def execute(
    db: AsyncSession,
    llm: LLMGateway,
    *,
    org_id: UUID,
    run_id: UUID,
    kit: tools.ToolKit | None = None,
) -> None:
    if not await flow_repo.claim_run(db, org_id=org_id, run_id=run_id):
        await db.rollback()
        return  # already running, finished or cancelled: a duplicate delivery does nothing
    await db.commit()
    began = time.monotonic()
    try:
        result = await _advance(
            db, llm, kit or tools.default_kit(), org_id=org_id, run_id=run_id
        )
    except _Stop:
        _log_end(run_id, began)
        return
    except BaseException as exc:
        crashed = isinstance(exc, Exception)
        logger.error("flow run stopped", extra={"error_type": type(exc).__name__})
        try:
            await db.rollback()
            if await flow_repo.fail_active_run(
                db,
                org_id=org_id,
                run_id=run_id,
                code="run_failed" if crashed else "worker_stopped",
            ):
                await _report(db, org_id=org_id, run_id=run_id)
            await db.commit()
        except BaseException:  # noqa: BLE001  (best effort; the stale-run sweep is the backstop)
            logger.error("could not record the stop of a flow run")
        if not crashed:
            raise
        return
    await flow_repo.finish_run(
        db, org_id=org_id, run_id=run_id, status="done", result=result
    )
    await _report(db, org_id=org_id, run_id=run_id)
    await db.commit()
    _log_end(run_id, began, "done")


async def _report(db: AsyncSession, *, org_id: UUID, run_id: UUID) -> None:
    """Tell the user in their Assistant conversation (ADR 0042, ``core.inbox``), in the caller's
    transaction: top-level runs only (not for_each children), and only a run this call ended (a
    cancel that landed first stays silent). The text holds the flow's name and a fixed code."""
    ended = await flow_repo.ended_top_run(db, org_id=org_id, run_id=run_id)
    if ended is None:
        return
    user_id, status, code, name = ended
    if user_id is None:
        return
    await inbox.post(
        db,
        org_id=org_id,
        user_id=user_id,
        kind="run_done" if status == "done" else "run_failed",
        params={"name": name, "code": code or ""},
        link=f"/automations/runs/{run_id}",
    )


def _log_end(run_id: UUID, began: float, status: str | None = None) -> None:
    """One metadata-only line per run (ids and timing, never content) for dashboards and alerts."""
    logger.info(
        "flow_run_ended",
        extra={
            "run_id": str(run_id),
            "outcome": status or "stopped",
            "duration_ms": int((time.monotonic() - began) * 1000),
        },
    )


async def _fail(
    db: AsyncSession,
    run: FlowRun,
    step: FlowRunStep | None,
    code: str,
) -> NoReturn:
    org_id, run_id = run.org_id, run.id  # a rollback expires the ORM rows
    step_id = step.id if step is not None else None
    await db.rollback()
    if step_id is not None:
        await flow_repo.set_step(
            db,
            org_id=org_id,
            step_id=step_id,
            status="failed",
            error_code=code,
        )
    await flow_repo.finish_run(
        db, org_id=org_id, run_id=run_id, status="failed", error_code=code
    )
    await _report(db, org_id=org_id, run_id=run_id)
    await db.commit()
    raise _Stop


async def _advance(
    db: AsyncSession,
    llm: LLMGateway,
    kit: tools.ToolKit,
    *,
    org_id: UUID,
    run_id: UUID,
) -> dict[str, Any]:
    run, graph, agents, steps, order = await _load_run(db, org_id=org_id, run_id=run_id)
    nodes = {n.id: n for n in graph.nodes}
    incoming: dict[UUID, list[g.Edge]] = {n: [] for n in nodes}
    for e in graph.edges:
        incoming[e.to].append(e)

    status: dict[UUID, str] = {nid: s.status for nid, s in steps.items()}
    outputs: dict[UUID, dict[str, Any]] = {
        nid: s.output or {} for nid, s in steps.items() if s.status == "done"
    }
    started = time.monotonic()
    result: dict[str, Any] = {}

    for nid in order:
        node, step = nodes[nid], steps[nid]
        if status[nid] == "done":
            if isinstance(node, g.OutputNode):
                result = outputs[nid]
            continue
        if status[nid] == "skipped":
            continue
        if status[nid] == "waiting":  # the run was woken: this wait is over
            output = {"value": (step.output or {}).get("value", "")}
            await flow_repo.set_step(
                db, org_id=org_id, step_id=step.id, only_if=("waiting",),
                status="done", output=output, finished_at=func.now(),
            )  # fmt: skip
            await db.commit()
            status[nid], outputs[nid] = "done", output
            continue
        await db.refresh(run)  # a cancel may have landed since the last step
        if run.status != "running":
            raise _Stop
        if time.monotonic() - started > RUN_TIMEOUT_S:
            await _fail(db, run, None, "run_timeout")

        await flow_repo.touch_run(db, org_id=org_id, run_id=run_id)
        active = [e for e in incoming[nid] if _is_active(e, status, outputs)]
        # An edge from a Condition's "if yes / if no" exit is a gate: a step with gates runs only
        # if one of them was taken. Without a gate, a step is skipped when nothing reaches it.
        gates = [e for e in incoming[nid] if e.from_.port in ("true", "false")]
        if incoming[nid] and (
            not active or (gates and not any(e in active for e in gates))
        ):
            await _skip(db, org_id, step, status, nid)
            continue

        values = await _gather_inputs(
            db,
            run,
            step,
            node,
            incoming[nid],
            active,
            outputs,
            org_id=org_id,
            run_id=run_id,
            nid=nid,
        )

        # A step whose required input comes only from a branch that was not taken has nothing to
        # work on: it is skipped like the branch, not failed.
        if incoming[nid] and any(
            req and name not in values for name, req in g.input_names(node, agents)
        ):
            await _skip(db, org_id, step, status, nid)
            continue

        if isinstance(node, g.ToolNode) and registry.get(node.tool).pauses:
            await _park(db, run, step, node, values.get("value", ""))

        output = await _execute_step(
            db, llm, kit, run, step, node, agents, values, org_id=org_id, run_id=run_id
        )
        status[nid], outputs[nid] = "done", output
        if isinstance(node, g.OutputNode):
            result = output
    return result


async def _load_run(
    db: AsyncSession, *, org_id: UUID, run_id: UUID
) -> tuple[
    FlowRun, g.Graph, dict[UUID, g.AgentInfo], dict[UUID, FlowRunStep], list[UUID]
]:
    """The claimed run, its pinned graph and helpers, its step rows, and the execution order."""
    run = await flow_repo.get_run(db, org_id=org_id, run_id=run_id)
    assert run is not None  # claimed a moment ago
    version = await flow_repo.get_flow_version_by_id(
        db, org_id=org_id, version_id=run.flow_version_id
    )
    assert version is not None
    graph = g.Graph.model_validate(version.graph)
    agents = await load_agents(db, org_id=org_id, graph=graph)
    nodes = {n.id: n for n in graph.nodes}
    steps = {
        s.node_id: s
        for s in await flow_repo.list_steps(db, org_id=org_id, run_id=run_id)
    }
    order = g.topological(graph)
    if order is None or set(steps) != set(nodes):
        await _fail(db, run, None, "invalid_flow")
    return run, graph, agents, steps, order


async def _skip(
    db: AsyncSession,
    org_id: UUID,
    step: FlowRunStep,
    status: dict[UUID, str],
    nid: UUID,
) -> None:
    await flow_repo.set_step(db, org_id=org_id, step_id=step.id, status="skipped")
    status[nid] = "skipped"
    await db.commit()


async def _gather_inputs(
    db: AsyncSession,
    run: FlowRun,
    step: FlowRunStep,
    node: Any,
    incoming: list[g.Edge],
    active: list[g.Edge],
    outputs: dict[UUID, dict[str, Any]],
    *,
    org_id: UUID,
    run_id: UUID,
    nid: UUID,
) -> dict[str, str]:
    """The step's input values from its active edges (each hand-off recorded) and typed text."""
    # text typed on a step fills an input no link maps; a link owns its input, so one on a branch
    # not taken leaves the input empty and the step is skipped as before
    mapped = {m.input for e in incoming for m in e.map}
    values: dict[str, str] = (
        {k: v for k, v in node.fixed.items() if k not in mapped}
        if isinstance(node, g.ToolNode)
        else {}
    )
    linked: set[str] = set()
    for e in active:
        payload, truncated = g.render_map(e.map, outputs[e.from_.node])
        for key in payload:
            if key in linked:  # two live edges into one input: never guess which wins
                await _fail(db, run, step, "ambiguous_input")
        linked.update(payload)
        values.update(payload)
        await flow_repo.record_handoff(
            db,
            org_id=org_id,
            values={
                "run_id": run_id,
                "edge_id": e.id,
                "from_node": e.from_.node,
                "to_node": nid,
                "payload": payload,
                "truncated": truncated,
            },
        )
    return values


async def _execute_step(
    db: AsyncSession,
    llm: LLMGateway,
    kit: tools.ToolKit,
    run: FlowRun,
    step: FlowRunStep,
    node: Any,
    agents: dict[UUID, g.AgentInfo],
    values: dict[str, str],
    *,
    org_id: UUID,
    run_id: UUID,
) -> dict[str, Any]:
    """Claim the step, run it, store its output. Raises ``_Stop`` if another worker has it."""
    if not await flow_repo.claim_step(db, org_id=org_id, step_id=step.id):
        raise _Stop  # another worker holds it
    await db.commit()

    output, model, latency = await _run_node(
        db, llm, kit, run, step, node, agents, values
    )
    if not await flow_repo.set_step(
        db,
        org_id=org_id,
        step_id=step.id,
        only_if=(
            "running",
        ),  # the run may have been resumed under us: never overwrite it
        status="done",
        output=output,
        model=model,
        latency_ms=latency,
        finished_at=func.now(),
    ):
        await db.rollback()
        raise _Stop
    await flow_repo.touch_run(db, org_id=org_id, run_id=run_id)
    await db.commit()
    return output


def _is_active(
    e: g.Edge, status: dict[UUID, str], outputs: dict[UUID, dict[str, Any]]
) -> bool:
    if status[e.from_.node] != "done":
        return False
    if e.from_.port in ("true", "false"):
        taken = "true" if outputs[e.from_.node].get("branch") else "false"
        return e.from_.port == taken
    return True


async def _run_node(
    db: AsyncSession,
    llm: LLMGateway,
    kit: tools.ToolKit,
    run: FlowRun,
    step: FlowRunStep,
    node: Any,
    agents: dict[UUID, g.AgentInfo],
    values: dict[str, str],
) -> tuple[dict[str, Any], str | None, int | None]:
    match node:
        case g.InputNode():
            return (
                {f.name: str(run.inputs.get(f.name, "")) for f in node.fields},
                None,
                None,
            )
        case g.OutputNode():
            return {f.name: values.get(f.name, "") for f in node.fields}, None, None
        case g.TransformNode():
            return {"text": g.apply_transform(node, values.get("text", ""))}, None, None
        case g.ConditionNode():
            try:
                holds = g.condition_holds(node, values.get("value", ""))
            except ValueError:
                await _fail(db, run, step, "condition_invalid")
            return {"value": values.get("value", ""), "branch": holds}, None, None
        case g.AgentNode():
            return await _run_agent(db, llm, run, step, node, agents, values)
        case g.ToolNode():
            return await _run_tool(db, llm, kit, run, step, node, values)
    await _fail(db, run, step, "unknown_node")


async def _run_tool(
    db: AsyncSession,
    llm: LLMGateway,
    kit: tools.ToolKit,
    run: FlowRun,
    step: FlowRunStep,
    node: g.ToolNode,
    values: dict[str, str],
) -> tuple[dict[str, Any], str | None, int | None]:
    began = time.monotonic()
    try:
        spec = registry.get(node.tool)
        if spec.flag and not getattr(
            get_settings(), spec.flag
        ):  # its pack was switched off
            await _fail(db, run, step, "tool_off")
        if spec.starts_runs and run.trigger == "flow":
            await _fail(
                db, run, step, "nested_not_allowed"
            )  # one level only, before any cap use
        caps = spec.cap
        if (
            caps is not None
        ):  # an outside effect: at most once per step, and capped per day
            if run.user_id is None:
                await _fail(db, run, step, "tool_failed")
            verdict = await flow_repo.claim_effect(
                db,
                org_id=run.org_id,
                user_id=run.user_id,
                run_id=run.id,
                node_id=step.node_id,
                kind=node.tool,
                daily_cap=caps.user,
                global_cap=caps.everyone,
                once=caps.once,
            )
            if verdict == "capped":
                await _fail(db, run, step, "daily_limit")
            if (
                verdict == "done"
            ):  # a resumed step: it already happened, do not repeat it
                await (
                    db.commit()
                )  # frees the lock; a rollback would expire every loaded row
                return {"status": "already done"}, None, 0
        output = (
            await _fan_out(db, run, node, values)
            if spec.starts_runs
            else await tools.run_tool(db, llm, kit, run, node, values)
        )
    except _Stop:
        raise
    except AppError as exc:
        await _fail(db, run, step, exc.code)
    except Exception as exc:  # noqa: BLE001  (a safe code, never exception text)
        logger.error("tool step failed", extra={"error_type": type(exc).__name__})
        await _fail(db, run, step, "tool_failed")
    return output, None, int((time.monotonic() - began) * 1000)


async def _fan_out(
    db: AsyncSession, run: FlowRun, node: g.ToolNode, values: dict[str, str]
) -> dict[str, str]:
    """Start one run of another flow per item; this step is done once they are queued."""
    # Lazy on purpose: flows.runs imports this module (import cycle, kept for now).
    from recruitai.modules.agents.flows import runs as flow_runs

    if node.flow_id is None:
        raise ToolFailed()
    try:
        items = json.loads(values.get("items") or "[]")
    except ValueError as exc:
        raise ToolFailed() from exc
    if not (
        isinstance(items, list)
        and len(items) <= tools.MAX_FAN_OUT
        and all(
            isinstance(i, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in i.items())
            for i in items
        )
    ):
        raise ToolFailed()
    await db.commit()  # nothing held open while the runs are queued
    runs = await flow_runs.fan_out(
        db,
        parent=run,
        flow_id=node.flow_id,
        items=items,
        daily_quota=get_settings().ai_daily_quota_per_user,
    )
    return {"started": str(len(runs)), "text": "\n".join(str(r.id) for r in runs)}


async def _run_agent(
    db: AsyncSession,
    llm: LLMGateway,
    run: FlowRun,
    step: FlowRunStep,
    node: g.AgentNode,
    agents: dict[UUID, g.AgentInfo],
    values: dict[str, str],
) -> tuple[dict[str, Any], str | None, int | None]:
    info = agents.get(node.agent_version_id)
    if info is None or info.agent_id != node.agent_id:
        await _fail(db, run, step, "agent_unavailable")
    try:
        context = await service.context_for(
            db, org_id=run.org_id, spec=info.spec, job_id=run.job_id
        )
        await db.commit()  # nothing held open across the model call
        outcome = await runner.run(
            llm,
            info.spec,
            values=values,
            context=context,
            feature=helper.feature(node.agent_id, info.version, info.spec.model_tier),
        )
    except AppError as exc:
        await _fail(db, run, step, exc.code)
    except Exception as exc:  # noqa: BLE001  (a safe code, never exception text)
        logger.error("helper step failed", extra={"error_type": type(exc).__name__})
        await _fail(db, run, step, "step_failed")
    return outcome.result, outcome.model, outcome.latency_ms
