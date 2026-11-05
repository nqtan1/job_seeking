"""The flow graph (ADR 0031): schema, validation and the data rules, with no I/O.

Identity rule: nodes and edges are UUIDs; wiring never uses a name. Isolation rule: a node's inputs
come ONLY from the ``map`` of its incoming edges, and an edge's templates may reference only the
fields of that edge's source node. There is nowhere else for data to travel. The editor preview and
the engine both call ``render_map``, so they cannot disagree."""

import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

from recruitai.modules.agents.schemas import (
    MAX_INPUT_CHARS,
    FieldName,
    InputField,
    VersionSpec,
)

SCHEMA_VERSION = 1
MAX_NODES = 15
MAX_EDGES = 30
MAX_MAPS = 10
MAX_TEMPLATE = 2_000
# Every helper step also takes this optional input, so anything can be handed to any helper (a helper
# that declares no input of its own would otherwise have nothing to receive).
EXTRA_INPUT = "info"
TOKEN = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,31})\s*\}\}")
ANY_BRACES = re.compile(r"\{\{|\}\}")
Template = Annotated[str, StringConstraints(max_length=MAX_TEMPLATE)]


class Position(BaseModel):
    x: float = 0
    y: float = 0


class _Node(BaseModel):
    id: UUID
    position: Position = Position()


def _unique(fields: list[InputField]) -> list[InputField]:
    if len({f.name for f in fields}) != len(fields):
        raise ValueError("duplicate field names")
    return fields


class InputNode(_Node):
    type: Literal["input"] = "input"
    fields: Annotated[
        list[InputField], Field(min_length=1, max_length=6), AfterValidator(_unique)
    ]


class OutputNode(_Node):
    type: Literal["output"] = "output"
    fields: Annotated[
        list[InputField], Field(min_length=1, max_length=6), AfterValidator(_unique)
    ]


class AgentNode(_Node):
    type: Literal["agent"] = "agent"
    agent_id: UUID
    agent_version_id: UUID


class ConditionNode(_Node):
    type: Literal["condition"] = "condition"
    op: Literal["eq", "neq", "contains", "gt", "lt"]
    value: str = Field(max_length=200)


class TransformNode(_Node):
    type: Literal["transform"] = "transform"
    op: Literal["trim", "truncate", "lower", "upper", "first_line"]
    arg: int | None = Field(None, ge=1, le=MAX_INPUT_CHARS)

    @model_validator(mode="after")
    def _arg(self) -> "TransformNode":
        if (self.op == "truncate") != (self.arg is not None):
            raise ValueError("only truncate takes a number")
        return self


# ADR 0032: a closed list of actions. Each has fixed inputs ``(name, required)`` and outputs; the user
# only chooses which one and wires the edges. There is no config a user could put a URL or code in.
ToolKind = Literal[
    "web_search",
    "job_search",
    "find_offers",
    "fit_check",
    "for_each",
    "read_page",
    "job_lookup",
    "add_to_tracker",
    "send_email",
    "wait",
]
TOOLS: dict[str, tuple[tuple[tuple[str, bool], ...], tuple[str, ...]]] = {
    "web_search": ((("query", True),), ("text", "sources")),
    "job_search": ((("query", True), ("department", False)), ("text", "count")),
    # new offers of a search (not yet saved as Jobs), saved with their full text; ``items`` is JSON,
    # one object per offer (job_id, title, company, place, url) for for_each
    "find_offers": (
        (("query", True), ("department", False)),
        ("items", "text", "count", "remaining"),
    ),
    # the fit analysis of the run's job (the app's tested fit prompts); "start" hangs it off Start
    "fit_check": (
        (("start", False), ("employer", False)),
        ("score", "verdict", "strengths", "gaps", "missing", "reasons"),
    ),
    # starts one run of another automation per item (ADR 0034); the items' keys fill its Start step
    "for_each": ((("items", True),), ("started", "text")),
    "read_page": ((("url", True),), ("text",)),
    # reads the run's chosen job; "start" is an optional link so it can hang off the Input step
    "job_lookup": (
        (("start", False),),
        ("title", "company", "place", "description", "url"),
    ),
    "add_to_tracker": (
        (("company", True), ("title", False), ("url", False), ("notes", False)),
        ("status",),
    ),
    "send_email": ((("to", True), ("subject", True), ("body", True)), ("status",)),
    "wait": ((("value", True),), ("value",)),  # passes its input on, later (see engine)
}


class ToolNode(_Node):
    type: Literal["tool"] = "tool"
    tool: ToolKind
    minutes: int | None = Field(None, ge=1, le=7 * 24 * 60)  # wait only
    flow_id: UUID | None = None  # for_each only: the automation started for each item

    @model_validator(mode="after")
    def _config(self) -> "ToolNode":
        if (self.tool == "wait") != (self.minutes is not None):
            raise ValueError("only wait takes minutes, and it needs them")
        if self.flow_id is not None and self.tool != "for_each":
            raise ValueError("only for_each takes a flow")
        return self


Node = Annotated[
    InputNode | OutputNode | AgentNode | ConditionNode | TransformNode | ToolNode,
    Field(discriminator="type"),
]


class End(BaseModel):
    node: UUID
    port: Literal["out", "true", "false"] = "out"


class MapEntry(BaseModel):
    input: FieldName
    value: Template


class Edge(BaseModel):
    id: UUID
    from_: End = Field(alias="from")
    to: UUID
    map: list[MapEntry] = Field(max_length=MAX_MAPS)

    model_config = {"populate_by_name": True}


class Graph(BaseModel):
    schema_version: Literal[1] = 1
    nodes: list[Node] = Field(max_length=MAX_NODES)
    edges: list[Edge] = Field(default=[], max_length=MAX_EDGES)


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    node_id: UUID | None = None
    edge_id: UUID | None = None
    severity: Literal["error", "warning"] = "error"


@dataclass(frozen=True)
class AgentInfo:
    """What the validator needs to know about a pinned helper version."""

    spec: VersionSpec
    agent_id: UUID | None = (
        None  # the helper that owns the version (None in pure unit tests)
    )
    version: int = 0  # its number, for the ai_calls label


def input_names(node: Any, agents: dict[UUID, AgentInfo]) -> list[tuple[str, bool]]:
    """``(name, required)`` of what a node takes in."""
    match node:
        case InputNode():
            return []
        case OutputNode():
            return [(f.name, False) for f in node.fields]
        case AgentNode():
            info = agents.get(node.agent_version_id)
            if info is None:
                return []
            own = [(i.name, i.required) for i in info.spec.inputs]
            return own if EXTRA_INPUT in dict(own) else [*own, (EXTRA_INPUT, False)]
        case ConditionNode():
            return [("value", True)]
        case TransformNode():
            return [("text", True)]
        case ToolNode():
            return list(TOOLS[node.tool][0])
    return []


def output_names(node: Any, agents: dict[UUID, AgentInfo]) -> list[str]:
    match node:
        case InputNode():
            return [f.name for f in node.fields]
        case AgentNode():
            info = agents.get(node.agent_version_id)
            if info is None:
                return []
            out = info.spec.output
            return ["text"] if out.kind == "text" else [f.name for f in out.fields]
        case ConditionNode():
            return ["value"]
        case TransformNode():
            return ["text"]
        case ToolNode():
            return list(TOOLS[node.tool][1])
    return []  # an output node is a sink


def topological(graph: Graph) -> list[UUID] | None:
    """Node ids in a stable execution order (graph order breaks ties), or None on a cycle."""
    order = {n.id: i for i, n in enumerate(graph.nodes)}
    indeg = {n.id: 0 for n in graph.nodes}
    out: dict[UUID, list[UUID]] = defaultdict(list)
    for e in graph.edges:
        if e.from_.node in indeg and e.to in indeg:
            out[e.from_.node].append(e.to)
            indeg[e.to] += 1
    ready = deque(
        sorted((n for n, d in indeg.items() if d == 0), key=order.__getitem__)
    )
    result: list[UUID] = []
    while ready:
        n = ready.popleft()
        result.append(n)
        for m in sorted(out[n], key=order.__getitem__):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    return result if len(result) == len(indeg) else None


def _owns(agents: dict[UUID, AgentInfo], node: "AgentNode") -> bool:
    """The pinned version exists and really belongs to the helper the node names."""
    info = agents.get(node.agent_version_id)
    return info is not None and info.agent_id in (None, node.agent_id)


def validate(graph: Graph, agents: dict[UUID, AgentInfo]) -> list[Issue]:
    """Every problem the graph has, with the node/edge to jump to. Server-side and authoritative."""
    issues: list[Issue] = []
    nodes = {n.id: n for n in graph.nodes}
    if len(nodes) != len(graph.nodes):
        return [Issue("duplicate_node_id", "Two steps share an id.")]
    edge_ids = [e.id for e in graph.edges]
    if len(set(edge_ids)) != len(edge_ids):
        return [Issue("duplicate_edge_id", "Two connections share an id.")]
    kinds = [n.type for n in graph.nodes]
    if kinds.count("input") != 1:
        issues.append(Issue("input_count", "A flow needs exactly one Input step."))
    if kinds.count("output") != 1:
        issues.append(Issue("output_count", "A flow needs exactly one Output step."))
    for n in graph.nodes:
        if isinstance(n, AgentNode) and not _owns(agents, n):
            issues.append(Issue("agent_unavailable", "This helper is missing.", n.id))

    # A missing helper hides its fields: report it once, not as a cascade of unknown names.
    blind = {
        n.id for n in graph.nodes if isinstance(n, AgentNode) and not _owns(agents, n)
    }
    fed: dict[UUID, set[str]] = defaultdict(set)
    ends_ok = True
    for e in graph.edges:
        src, dst = nodes.get(e.from_.node), nodes.get(e.to)
        if src is None or dst is None:
            issues.append(
                Issue("dangling_edge", "A connection has no end.", None, e.id)
            )
            ends_ok = False
            continue
        if e.from_.node == e.to:
            issues.append(
                Issue("self_edge", "A step cannot feed itself.", dst.id, e.id)
            )
            ends_ok = False
            continue
        if isinstance(src, OutputNode) or isinstance(dst, InputNode):
            issues.append(
                Issue("bad_direction", "Wrong connection direction.", None, e.id)
            )
            ends_ok = False
            continue
        branch = isinstance(src, ConditionNode)
        if branch != (e.from_.port in ("true", "false")):
            issues.append(
                Issue(
                    "bad_port",
                    "Only a Condition has true/false exits.",
                    src.id,
                    e.id,
                )
            )
        sources = set(output_names(src, agents))
        targets = {name for name, _ in input_names(dst, agents)}
        seen: set[str] = set()
        for m in e.map:
            if m.input not in targets and dst.id not in blind:
                issues.append(
                    Issue(
                        "unknown_input",
                        f"“{m.input}” is not an input there.",
                        dst.id,
                        e.id,
                    )
                )
            if m.input in seen:
                issues.append(
                    Issue(
                        "duplicate_input", f"“{m.input}” is mapped twice.", dst.id, e.id
                    )
                )
            seen.add(m.input)
            fed[dst.id].add(m.input)
            leftovers = TOKEN.sub("", m.value)
            if ANY_BRACES.search(leftovers):
                issues.append(
                    Issue("bad_template", "Malformed {{ }} in a value.", dst.id, e.id)
                )
            for field in TOKEN.findall(m.value):
                if field not in sources and src.id not in blind:
                    issues.append(
                        Issue(
                            "unknown_field",
                            f"“{field}” is not an output of the previous step.",
                            dst.id,
                            e.id,
                        )
                    )
    issues += _shared_inputs(graph, nodes)
    for n in graph.nodes:
        for name, required in input_names(n, agents):
            if required and name not in fed[n.id] and n.id not in blind:
                issues.append(
                    Issue("unmapped_input", f"Input “{name}” is not connected.", n.id)
                )

    if ends_ok and not any(i.code in ("input_count", "output_count") for i in issues):
        if topological(graph) is None:
            issues.append(Issue("cycle", "The flow loops back on itself."))
        else:
            issues += _reachability(graph, nodes)
    return issues


def _shared_inputs(graph: Graph, nodes: dict[UUID, Any]) -> list[Issue]:
    """Two links into one input are legitimate only as the two exits of one Condition (a merge);
    otherwise the engine would have to guess which wins, so it is an error before any AI is spent."""
    feeders: dict[tuple[UUID, str], list[Edge]] = defaultdict(list)
    for e in graph.edges:
        for m in e.map:
            feeders[(e.to, m.input)].append(e)
    out: list[Issue] = []
    for (to, name), edges in feeders.items():
        if len(edges) < 2:
            continue
        branches = {(e.from_.node, e.from_.port) for e in edges}
        sources = {e.from_.node for e in edges}
        exclusive = (
            len(edges) == 2
            and len(sources) == 1
            and isinstance(nodes.get(next(iter(sources))), ConditionNode)
            and len(branches) == 2
        )
        if not exclusive:
            out.append(
                Issue(
                    "shared_input",
                    f"“{name}” is fed by two links at once.",
                    to,
                    edges[1].id,
                )
            )
    return out


def _reachability(graph: Graph, nodes: dict[UUID, Any]) -> list[Issue]:
    fwd: dict[UUID, list[UUID]] = defaultdict(list)
    back: dict[UUID, list[UUID]] = defaultdict(list)
    for e in graph.edges:
        fwd[e.from_.node].append(e.to)
        back[e.to].append(e.from_.node)

    def reach(start: list[UUID], adj: dict[UUID, list[UUID]]) -> set[UUID]:
        seen, stack = set(start), list(start)
        while stack:
            for m in adj[stack.pop()]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        return seen

    entry = [
        n.id
        for n in graph.nodes
        if n.type == "input" or (isinstance(n, ToolNode) and n.tool == "job_lookup")
    ]
    exit_ = [n.id for n in graph.nodes if n.type == "output"]
    from_input, to_output = reach(entry, fwd), reach(exit_, back)
    issues = []
    for n in graph.nodes:
        if n.id not in from_input:
            issues.append(
                Issue("unreachable", "This step gets nothing from Input.", n.id)
            )
        elif n.id not in to_output:
            issues.append(
                Issue(
                    "dead_end",
                    "This step's result is never used.",
                    n.id,
                    None,
                    "warning",
                )
            )
    return issues


# data rules, shared by the engine and the editor preview


def _text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "\n".join(f"- {_text(v)}" for v in value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def render_map(
    entries: list[MapEntry], outputs: dict[str, Any]
) -> tuple[dict[str, str], bool]:
    """One hand-off: the values the target receives, and whether any was cut at the cap.
    ``outputs`` is the source node's output, the only thing a template can read."""
    out: dict[str, str] = {}
    truncated = False
    for m in entries:
        text = TOKEN.sub(lambda t: _text(outputs.get(t.group(1))), m.value)
        if len(text) > MAX_INPUT_CHARS:
            text, truncated = text[:MAX_INPUT_CHARS], True
        out[m.input] = text
    return out, truncated


def apply_transform(node: TransformNode, text: str) -> str:
    match node.op:
        case "trim":
            return text.strip()
        case "lower":
            return text.lower()
        case "upper":
            return text.upper()
        case "first_line":
            return text.strip().split("\n", 1)[0]
        case "truncate":
            return text[: node.arg or 0]
    return text


def condition_holds(node: ConditionNode, text: str) -> bool:
    """Raises ValueError for a numeric test on text: the step fails loudly, it never guesses."""
    match node.op:
        case "eq":
            return text.strip().casefold() == node.value.strip().casefold()
        case "neq":
            return text.strip().casefold() != node.value.strip().casefold()
        case "contains":
            return node.value.casefold() in text.casefold()
        case "gt" | "lt":
            left, right = float(text.strip()), float(node.value.strip())
            if not (math.isfinite(left) and math.isfinite(right)):
                raise ValueError("not a finite number")
            return left > right if node.op == "gt" else left < right
    return False
