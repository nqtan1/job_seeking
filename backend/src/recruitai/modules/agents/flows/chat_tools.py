"""Routines from chat (ADR 0042, PA-07): two write tools the assistant proposes and the user confirms.
``set_up_job_hunter`` fills the ready-made job hunter (ADR 0035) and its daily schedule;
``run_routine`` starts one of the user's flows, as "Run now" does. No graph is generated:
both only fill what already exists. Chat only (``Tool.chat_only``): never a flow step.
``hunter_args`` and ``routine_args`` are what the chat stores on the card, so the card shows
exactly what the handler then runs (PA-11)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core import tools as registry
from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.tools import Call, Cap, Tool, ToolFailed, register
from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import repository as repo
from recruitai.modules.agents.flows import runs as flow_runs
from recruitai.modules.agents.flows import schedules, starters
from recruitai.modules.agents.flows import service as flows
from recruitai.modules.agents.flows.models import Flow, FlowSchedule
from recruitai.modules.agents.flows.schemas import RunIn, ScheduleIn

DEFAULT_HOUR = 8
# ponytail: no stored user time zone yet; the user's other schedules give theirs, else this one
DEFAULT_TZ = "Europe/Paris"


class RoutineNotFound(ToolFailed):
    code = "routine_not_found"
    default_detail = "No flow has that name."


class RoutineAmbiguous(ToolFailed):
    code = "routine_ambiguous"
    default_detail = "Several flows match that name: say which one."


class RoutineHasOutsideSteps(ToolFailed):
    code = "routine_has_outside_steps"
    default_detail = "That flow sends messages: run it from its own page."


def _number(raw: str, default: int, low: int, high: int) -> int:
    try:
        return min(max(int(raw.strip()), low), high)
    except ValueError:
        return default


def hunter_args(values: dict[str, str]) -> dict[str, str]:
    """The job hunter's inputs as its handler uses them (clamped, defaulted): stored on the card."""
    return {
        "query": values.get("query", "").strip(),
        "min_fit": str(_number(values.get("min_fit", ""), starters.MIN_FIT, 0, 100)),
        "hour": str(_number(values.get("hour", ""), DEFAULT_HOUR, 0, 23)),
    }


async def _zone(c: Call) -> str:
    """The time zone of the user's newest schedule (the web sends the browser's), else the default."""
    rows = await repo.schedules_for_org(c.db, org_id=c.org_id)
    mine = [s for s in rows if s.user_id == c.user_id]
    return max(mine, key=lambda s: s.created_at).timezone if mine else DEFAULT_TZ


async def _daily(c: Call, flow: Flow, query: str, hour: int) -> FlowSchedule:
    """One daily schedule of the hunter: the first one is updated in place, else one is made."""
    assert c.user_id is not None
    existing = await repo.list_schedules(c.db, org_id=c.org_id, flow_id=flow.id)
    tz = existing[0].timezone if existing else await _zone(c)
    data = ScheduleIn(
        cadence="daily",
        at_time=f"{hour:02d}:00",
        weekday=None,
        timezone=tz,
        inputs={"query": query},
        job_id=None,
    )
    if not existing:
        return await schedules.create_schedule(
            c.db, org_id=c.org_id, user_id=c.user_id, flow_id=flow.id, data=data
        )
    s = existing[0]
    await flow_runs.prepare_run(
        c.db, org_id=c.org_id, flow_id=flow.id, data=RunIn(inputs=data.inputs)
    )
    values: dict[str, Any] = {
        "cadence": "daily",
        "at_time": data.at_time,
        "weekday": None,
        "inputs": dict(data.inputs),
        "enabled": True,
        "paused_reason": None,
        "consecutive_failures": 0,
        "next_run_at": schedules.next_run(
            "daily", data.at_time, None, tz, datetime.now(UTC)
        ),
    }
    await repo.update_schedule(c.db, org_id=c.org_id, schedule_id=s.id, values=values)
    await c.db.commit()
    return s


async def _set_up_job_hunter(c: Call) -> dict[str, str]:
    if c.user_id is None:
        raise ToolFailed()
    args = hunter_args(c.values)
    if not (query := args["query"]):
        raise ValidationFailed("Say what to search for.")
    min_fit, hour = int(args["min_fit"]), int(args["hour"])
    flow, version = await starters.install_job_hunter(
        c.db, org_id=c.org_id, min_fit=min_fit
    )
    # an edited hunter keeps its own threshold
    await starters.set_min_fit(c.db, org_id=c.org_id, hunter=version, min_fit=min_fit)
    schedule = await _daily(c, flow, query, hour)
    return {"flow_id": str(flow.id), "schedule_id": str(schedule.id)}


def match(flows_: list[Flow], name: str) -> Flow:
    """One flow by name, ignoring case: an exact name wins, else a unique prefix."""
    wanted = " ".join(name.split()).casefold()
    for test in (str.__eq__, str.startswith):
        hits = [f for f in flows_ if test(" ".join(f.name.split()).casefold(), wanted)]
        if len(hits) == 1:
            return hits[0]
        if hits:
            raise RoutineAmbiguous()
    raise RoutineNotFound()


async def _leaves_app(
    db: AsyncSession, org_id: UUID, graph: g.Graph, *, nested: bool = True
) -> bool:
    """A step that sends something out (e-mail, Telegram), here or in a flow it starts (one level
    deep, like for_each): ADR 0042 keeps those out of chat."""
    for n in graph.nodes:
        if not isinstance(n, g.ToolNode):
            continue
        tool = registry.get(n.tool)
        if tool.effect == "outside":
            return True
        if nested and tool.starts_runs and n.flow_id is not None:
            try:
                _, target = await flows.get_detail(db, org_id=org_id, flow_id=n.flow_id)
            except NotFound:
                continue
            if await _leaves_app(db, org_id, flows.graph_of(target), nested=False):
                return True
    return False


async def routine(db: AsyncSession, *, org_id: UUID, flow_id: str, name: str) -> Flow:
    """The flow ``run_routine`` starts: by id (the card's), else by the model's name. A live flow
    of this org with no outside step, else a fixed code."""
    if not flow_id:
        if not name.strip():
            raise RoutineNotFound()
        flow_id = str(match(await flows.list_flows(db, org_id=org_id), name).id)
    try:
        flow, version = await flows.get_detail(db, org_id=org_id, flow_id=UUID(flow_id))
    except (NotFound, ValueError):
        raise RoutineNotFound() from None
    if flow.archived_at is not None:
        raise RoutineNotFound()
    if await _leaves_app(db, org_id, flows.graph_of(version)):
        raise RoutineHasOutsideSteps()
    return flow


async def routine_args(
    db: AsyncSession, org_id: UUID, values: dict[str, str]
) -> dict[str, str]:
    """What a ``run_routine`` card stores: the resolved flow's id and real name."""
    flow = await routine(db, org_id=org_id, flow_id="", name=values.get("name", ""))
    return {"name": flow.name, "flow_id": str(flow.id)}


async def _run_routine(c: Call) -> dict[str, str]:
    if c.user_id is None:
        raise ToolFailed()
    flow = await routine(
        c.db, org_id=c.org_id, flow_id=c.get("flow_id"), name=c.get("name")
    )
    # the inputs it is scheduled with (the hunter's search), so "run my job hunter" just works
    saved = await repo.list_schedules(c.db, org_id=c.org_id, flow_id=flow.id)
    data = (
        RunIn(inputs=dict(saved[0].inputs), job_id=saved[0].job_id)
        if saved
        else RunIn(job_id=c.job_id)
    )
    run, _ = await flow_runs.start_run(
        c.db,
        org_id=c.org_id,
        user_id=c.user_id,
        flow_id=flow.id,
        data=data,
        idempotency_key=None,
    )
    return {"run_id": str(run.id)}


for _tool, _handler in (
    (
        Tool(
            "set_up_job_hunter",
            "core",
            (("query", True), ("min_fit", False), ("hour", False)),
            ("flow_id", "schedule_id"),
            effect="write",
            cap=Cap(3),
            chat=True,
            chat_only=True,
            flag="helpers_enabled",
        ),
        _set_up_job_hunter,
    ),
    (
        Tool(
            "run_routine",
            "core",
            (("name", True),),
            ("run_id",),
            effect="write",
            cap=Cap(20),
            chat=True,
            chat_only=True,
            flag="helpers_enabled",
        ),
        _run_routine,
    ),
):
    register(_tool, _handler)
