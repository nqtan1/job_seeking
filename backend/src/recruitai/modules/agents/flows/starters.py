"""Ready-made automations (ADR 0035): the job hunter, installed in one click.

"Job hunter" takes a search typed as a sentence ("AI engineer in Paris", "ingénieur IA à Lyon"),
saves the new offers, and starts "Offer processor" for each: fit check, then (above 60) cover
letter, interview preparation, CV advice and a tracker card. Everything is built from the same
parts a user could assemble by hand, so it stays editable."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import NotFound
from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import service as flows
from recruitai.modules.agents.flows.models import Flow, FlowVersion
from recruitai.modules.agents.flows.schemas import FlowCreate, FlowVersionCreate
from recruitai.modules.agents.helpers import service
from recruitai.modules.agents.helpers.schemas import AgentCreate, VersionSpec

HUNTER = "Job hunter"
PROCESSOR = "Offer processor"
MIN_FIT = 60
PROCESSOR_TEXT = (
    "One saved offer: fit check, then letter, interview prep, CV advice and a tracker card if "
    "the fit is above {}."
)
ROLE_HELPERS = (
    (
        "letter",
        "Cover letter",
        "A cover letter from your profile, the job and its fit.",
    ),
    ("interview", "Interview prep", "Likely questions, topics to revise, context."),
    ("cv_advice", "CV advice", "How to adapt your CV to the job."),
)


def _edge(
    src: UUID, dst: UUID, *maps: tuple[str, str], port: str = "out"
) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "from": {"node": src, "port": port},
        "to": dst,
        "map": [{"input": i, "value": v} for i, v in maps],
    }


def _field(name: str, label: str, required: bool = False) -> dict[str, Any]:
    return {"name": name, "label": label, "required": required}


def _processor(helpers: dict[str, tuple[UUID, UUID]], min_fit: int) -> g.Graph:
    n = {
        k: uuid4()
        for k in (
            "start",
            "fit",
            "cond",
            "letter",
            "interview",
            "cv_advice",
            "track",
            "out",
        )
    }
    agents = [
        {
            "id": n[role],
            "type": "agent",
            "agent_id": helpers[role][0],
            "agent_version_id": helpers[role][1],
            "position": {"x": 840, "y": 150 * i},
        }
        for i, role in enumerate(("letter", "interview", "cv_advice"))
    ]
    nodes = [
        {"id": n["start"], "type": "input", "position": {"x": 0, "y": 200},
         "fields": [_field("title", "Job title"), _field("company", "Company")]},
        {"id": n["fit"], "type": "tool", "tool": "fit_check", "position": {"x": 280, "y": 200}},
        {"id": n["cond"], "type": "condition", "op": "gt", "value": str(min_fit),
         "position": {"x": 560, "y": 200}},
        *agents,
        {"id": n["track"], "type": "tool", "tool": "add_to_tracker", "position": {"x": 840, "y": 450}},
        {"id": n["out"], "type": "output", "position": {"x": 1120, "y": 200}, "fields": [
            _field("score", "Fit score"), _field("letter", "Cover letter"),
            _field("questions", "Interview questions"), _field("study", "What to revise"),
            _field("cv_changes", "CV changes"), _field("card", "Tracker card")]},
    ]  # fmt: skip
    edges = [
        _edge(n["start"], n["fit"], ("start", "{{title}}")),
        _edge(n["fit"], n["cond"], ("value", "{{score}}")),
        _edge(n["fit"], n["out"], ("score", "{{score}}")),
        *(_edge(n["cond"], n[k], port="true") for k in ("letter", "interview", "cv_advice", "track")),
        _edge(n["start"], n["track"], ("company", "{{company}}"), ("title", "{{title}}")),
        _edge(n["letter"], n["out"], ("letter", "{{text}}")),
        _edge(n["interview"], n["out"], ("questions", "{{questions}}"), ("study", "{{topics_to_study}}")),
        _edge(n["cv_advice"], n["out"], ("cv_changes", "{{cv_changes}}")),
        _edge(n["track"], n["out"], ("card", "{{status}}")),
    ]  # fmt: skip
    return g.Graph.model_validate({"nodes": nodes, "edges": edges})


def _hunter(processor_id: UUID) -> g.Graph:
    n = {k: uuid4() for k in ("start", "find", "each", "out")}
    nodes = [
        {"id": n["start"], "type": "input", "position": {"x": 0, "y": 100},
         "fields": [_field("query", "Search, e.g. AI engineer in Paris", True)]},
        {"id": n["find"], "type": "tool", "tool": "find_offers", "position": {"x": 280, "y": 100}},
        {"id": n["each"], "type": "tool", "tool": "for_each", "flow_id": processor_id,
         "position": {"x": 560, "y": 100}},
        {"id": n["out"], "type": "output", "position": {"x": 840, "y": 100}, "fields": [
            _field("found", "New offers saved"), _field("started", "Runs started")]},
    ]  # fmt: skip
    edges = [
        _edge(n["start"], n["find"], ("query", "{{query}}")),
        _edge(n["find"], n["each"], ("items", "{{items}}")),
        _edge(n["find"], n["out"], ("found", "{{count}}")),
        _edge(n["each"], n["out"], ("started", "{{started}}")),
    ]  # fmt: skip
    return g.Graph.model_validate({"nodes": nodes, "edges": edges})


async def install_job_hunter(
    db: AsyncSession, *, org_id: UUID, min_fit: int = MIN_FIT
) -> tuple[Flow, FlowVersion]:
    """Creates the three built-in helpers and the two automations. Asking twice returns the hunter
    that already exists instead of making a second set."""
    existing, versions = await flows.list_with_versions(db, org_id=org_id)
    for f in existing:
        if f.name == HUNTER and f.id in versions:
            return f, versions[f.id]
    helpers: dict[str, tuple[UUID, UUID]] = {}
    for role, name, description in ROLE_HELPERS:
        agent, version = await service.create_agent(
            db,
            org_id=org_id,
            data=AgentCreate(
                name=name,
                description=description,
                spec=VersionSpec.model_validate({"role": role, "model_tier": "smart"}),
                note="job hunter",
            ),
        )
        helpers[role] = (agent.id, version.id)
    processor, _ = await flows.create_flow(
        db,
        org_id=org_id,
        data=FlowCreate(
            name=PROCESSOR,
            description=PROCESSOR_TEXT.format(min_fit),
            graph=_processor(helpers, min_fit),
            note="job hunter",
        ),
    )
    return await flows.create_flow(
        db,
        org_id=org_id,
        data=FlowCreate(
            name=HUNTER,
            description="Type a search; new offers are saved and each one is prepared for you.",
            graph=_hunter(processor.id),
            note="job hunter",
        ),
    )


async def set_min_fit(
    db: AsyncSession, *, org_id: UUID, hunter: FlowVersion, min_fit: int
) -> bool:
    """The fit above which the processor prepares an offer, saved as a new version when it
    changed. False: the user edited the automations and there is no such step to set."""
    each = next(
        (
            n
            for n in flows.graph_of(hunter).nodes
            if isinstance(n, g.ToolNode) and n.flow_id
        ),
        None,
    )
    if each is None or each.flow_id is None:
        return False
    try:
        processor, version = await flows.get_detail(
            db, org_id=org_id, flow_id=each.flow_id
        )
    except NotFound:
        return False
    graph = flows.graph_of(version)
    cond = next((n for n in graph.nodes if isinstance(n, g.ConditionNode)), None)
    if cond is None or processor.archived_at is not None:
        return False
    if cond.value != str(min_fit):
        cond.value = str(min_fit)
        await flows.add_version(
            db,
            org_id=org_id,
            flow_id=processor.id,
            data=FlowVersionCreate(
                based_on=processor.current_version, graph=graph, note="job hunter"
            ),
        )
        await flows.patch_flow(
            db,
            org_id=org_id,
            flow_id=processor.id,
            name=None,
            description=PROCESSOR_TEXT.format(min_fit),
        )
    return True
