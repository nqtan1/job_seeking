"""The flow graph rules (ADR 0031): validation, hand-off rendering, conditions. No I/O."""

import re
from pathlib import Path
from uuid import uuid4

import pytest

from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import schedules
from recruitai.modules.agents.helpers import schemas, service
from recruitai.modules.agents.helpers.schemas import VersionSpec

SPEC = VersionSpec(
    instructions="x",
    inputs=[
        {"name": "notes", "label": "Notes"},
        {"name": "extra", "label": "E", "required": False},
    ],
)
AGENT_VERSION = uuid4()
AGENTS = {AGENT_VERSION: g.AgentInfo(spec=SPEC)}


def ids(n: int) -> list:
    return [uuid4() for _ in range(n)]


def make(edges_extra=None, drop_edge=False):
    """input -> agent -> output, the smallest valid flow."""
    i, a, o = ids(3)
    nodes = [
        {"type": "input", "id": i, "fields": [{"name": "n", "label": "N"}]},
        {
            "type": "agent",
            "id": a,
            "agent_id": uuid4(),
            "agent_version_id": AGENT_VERSION,
        },
        {"type": "output", "id": o, "fields": [{"name": "r", "label": "R"}]},
    ]
    edges = [
        {
            "id": uuid4(),
            "from": {"node": i},
            "to": a,
            "map": [{"input": "notes", "value": "{{n}}"}],
        },
        {
            "id": uuid4(),
            "from": {"node": a},
            "to": o,
            "map": [{"input": "r", "value": "{{text}}"}],
        },
    ]
    if drop_edge:
        edges.pop(0)
    return {"nodes": nodes, "edges": edges + (edges_extra or [])}, (i, a, o)


def codes(raw) -> set[str]:
    return {x.code for x in g.validate(g.Graph.model_validate(raw), AGENTS)}


def test_the_smallest_flow_is_valid_and_orders_input_first():
    raw, (i, a, o) = make()
    graph = g.Graph.model_validate(raw)
    assert g.validate(graph, AGENTS) == [] and g.topological(graph) == [i, a, o]


def test_every_kind_of_broken_flow_is_reported_with_a_stable_code():
    raw, (i, a, o) = make()
    back = {"id": uuid4(), "from": {"node": o}, "to": a, "map": []}
    assert "bad_direction" in codes({**raw, "edges": raw["edges"] + [back]})
    loop = {"id": uuid4(), "from": {"node": a}, "to": a, "map": []}
    assert "self_edge" in codes({**raw, "edges": raw["edges"] + [loop]})
    # a real cycle: a -> b -> a
    b = {"type": "transform", "id": uuid4(), "op": "trim"}
    cyc = [
        {
            "id": uuid4(),
            "from": {"node": a},
            "to": b["id"],
            "map": [{"input": "text", "value": "{{text}}"}],
        },
        {
            "id": uuid4(),
            "from": {"node": b["id"]},
            "to": a,
            "map": [{"input": "extra", "value": "{{text}}"}],
        },
    ]
    assert "cycle" in codes({"nodes": raw["nodes"] + [b], "edges": raw["edges"] + cyc})
    assert "unmapped_input" in codes(make(drop_edge=True)[0])
    bad_field = {
        "id": uuid4(),
        "from": {"node": i},
        "to": a,
        "map": [{"input": "extra", "value": "{{nope}}"}],
    }
    assert "unknown_field" in codes({**raw, "edges": raw["edges"] + [bad_field]})
    bad_input = {
        "id": uuid4(),
        "from": {"node": i},
        "to": a,
        "map": [{"input": "ghost", "value": "x"}],
    }
    assert "unknown_input" in codes({**raw, "edges": raw["edges"] + [bad_input]})
    broken = {
        "id": uuid4(),
        "from": {"node": i},
        "to": a,
        "map": [{"input": "extra", "value": "{{n"}],
    }
    assert "bad_template" in codes({**raw, "edges": raw["edges"] + [broken]})
    twice = {
        "id": uuid4(),
        "from": {"node": i},
        "to": a,
        "map": [{"input": "extra", "value": "a"}, {"input": "extra", "value": "b"}],
    }
    assert "duplicate_input" in codes({**raw, "edges": raw["edges"] + [twice]})
    port = {"id": uuid4(), "from": {"node": i, "port": "true"}, "to": a, "map": []}
    assert "bad_port" in codes({**raw, "edges": raw["edges"] + [port]})
    orphan = {"type": "transform", "id": uuid4(), "op": "trim"}
    assert "unreachable" in codes({**raw, "nodes": raw["nodes"] + [orphan]})
    dangling = {"id": uuid4(), "from": {"node": i}, "to": uuid4(), "map": []}
    assert "dangling_edge" in codes({**raw, "edges": raw["edges"] + [dangling]})
    dup = {**raw, "nodes": raw["nodes"] + [raw["nodes"][0]]}
    assert codes(dup) == {"duplicate_node_id"}
    assert codes({**raw, "nodes": raw["nodes"][1:]}) >= {"input_count"}
    unknown_agent = {
        **raw,
        "nodes": [
            raw["nodes"][0],
            {**raw["nodes"][1], "agent_version_id": uuid4()},
            raw["nodes"][2],
        ],
    }
    assert "agent_unavailable" in codes(unknown_agent)


def test_size_limits_are_part_of_the_schema():
    raw, _ = make()
    many = {
        **raw,
        "nodes": raw["nodes"]
        + [
            {"type": "transform", "id": uuid4(), "op": "trim"}
            for _ in range(g.MAX_NODES)
        ],
    }
    with pytest.raises(ValueError):
        g.Graph.model_validate(many)
    with pytest.raises(ValueError):
        g.Graph.model_validate(
            {"nodes": [{"type": "transform", "id": uuid4(), "op": "truncate"}]}
        )


def test_a_handoff_reads_only_the_sources_fields_and_caps_its_size():
    entries = [
        g.MapEntry(input="a", value="Hi {{who}}: {{items}} {{ok}} {{n}}"),
        g.MapEntry(input="b", value="{{big}}"),
    ]
    out, truncated = g.render_map(
        entries,
        {
            "who": "Ada",
            "items": ["x", "y"],
            "ok": True,
            "n": 3.0,
            "big": "z" * 25_000,
            "secret": "S",
        },
    )
    assert out["a"] == "Hi Ada: - x\n- y true 3" and "S" not in out["a"]
    assert len(out["b"]) == 20_000 and truncated
    assert g.render_map([g.MapEntry(input="a", value="{{missing}}")], {})[0] == {
        "a": ""
    }


def test_conditions_never_guess_and_transforms_are_closed_operations():
    cond = lambda op, v: g.ConditionNode(id=uuid4(), op=op, value=v)
    assert g.condition_holds(cond("eq", "YES"), " yes ")
    assert g.condition_holds(cond("contains", "risk"), "High RISK here")
    assert g.condition_holds(cond("gt", "3"), "10") and not g.condition_holds(
        cond("lt", "3"), "10"
    )
    with pytest.raises(ValueError):
        g.condition_holds(
            cond("gt", "3"), "many"
        )  # a numeric test on text fails loudly
    t = lambda op, arg=None: g.TransformNode(id=uuid4(), op=op, arg=arg)
    assert g.apply_transform(t("trim"), "  a ") == "a"
    assert g.apply_transform(t("truncate", 2), "abcd") == "ab"
    assert g.apply_transform(t("first_line"), "one\ntwo") == "one"


def test_two_links_into_one_input_are_only_allowed_as_the_two_exits_of_one_condition():
    i, c, a, o = ids(4)
    base = [
        {"type": "input", "id": i, "fields": [{"name": "n", "label": "N"}]},
        {"type": "condition", "id": c, "op": "eq", "value": "x"},
        {"type": "transform", "id": a, "op": "trim"},
        {"type": "output", "id": o, "fields": [{"name": "r", "label": "R"}]},
    ]
    feed = lambda src, port="out", to=a: {
        "id": uuid4(), "from": {"node": src, "port": port}, "to": to, "map": [{"input": "text", "value": "{{value}}"}],
    }  # fmt: skip
    head = {
        "id": uuid4(),
        "from": {"node": i},
        "to": c,
        "map": [{"input": "value", "value": "{{n}}"}],
    }
    tail = {
        "id": uuid4(),
        "from": {"node": a},
        "to": o,
        "map": [{"input": "r", "value": "{{text}}"}],
    }
    merge = {"nodes": base, "edges": [head, feed(c, "true"), feed(c, "false"), tail]}
    assert "shared_input" not in codes(merge)  # a legitimate merge of the two exits
    both = {"nodes": base, "edges": [head, feed(c, "true"), feed(c, "true"), tail]}
    assert "shared_input" in codes(both)
    two_sources = {**merge, "edges": [head, feed(c, "true"), feed(i), tail]}
    assert "shared_input" in codes(two_sources)


def test_names_that_would_collide_are_refused_up_front():
    with pytest.raises(ValueError):
        g.Graph.model_validate(
            {
                "nodes": [
                    {
                        "type": "input",
                        "id": uuid4(),
                        "fields": [
                            {"name": "a", "label": "x"},
                            {"name": "a", "label": "y"},
                        ],
                    }
                ]
            }
        )
    for bad in ("copy", "parse_obj", "model_x", "job", "profile", "fit"):
        with pytest.raises(ValueError):
            VersionSpec(instructions="x", inputs=[{"name": bad, "label": "x"}])
    cond = g.ConditionNode(id=uuid4(), op="gt", value="1")
    with pytest.raises(ValueError):
        g.condition_holds(cond, "nan")  # never a silent false


LIMITS = Path(__file__).parents[3] / "web/src/features/helpers/graph.ts"


def test_the_web_limits_equal_the_servers():
    web = {
        name: int(value.replace("_", ""))
        for name, value in re.findall(
            r"export const (\w+) = ([\d_]+)", LIMITS.read_text()
        )
    }
    assert web == {
        "MAX_INPUT_CHARS": schemas.MAX_INPUT_CHARS,
        "MAX_INPUTS": schemas.MAX_INPUTS,
        "MAX_FIELDS": schemas.MAX_FIELDS,
        "MAX_NODES": g.MAX_NODES,
        "MAX_EDGES": g.MAX_EDGES,
        "MAX_FIXED_CHARS": g.MAX_FIXED_CHARS,
        "MAX_HELPERS": service.MAX_AGENTS_PER_ORG,
        "MAX_SCHEDULES": schedules.MAX_SCHEDULES_PER_ORG,
    }


def test_time_zones_do_not_depend_on_the_system_database():
    """The Docker images are python:slim (no /usr/share/zoneinfo): schedules need the tzdata package."""
    import importlib

    importlib.import_module("tzdata")
