"""A page address built from AI or web text is only warned about, never blocked."""

from uuid import uuid4

from recruitai.modules.agents.flows import graph as g
from tests.unit.test_flow_graph import AGENTS, make


def test_a_page_address_taken_from_untrusted_text_gets_a_warning_only():
    raw, (i, a, _) = make()
    read = {"type": "tool", "id": uuid4(), "tool": "read_page"}
    link = lambda src, value: {
        "id": uuid4(), "from": {"node": src}, "to": read["id"],
        "map": [{"input": "url", "value": value}],
    }  # fmt: skip

    def issues(src, value):
        graph = g.Graph.model_validate(
            {"nodes": raw["nodes"] + [read], "edges": raw["edges"] + [link(src, value)]}
        )
        return [x for x in g.validate(graph, AGENTS) if x.code == "untrusted_url"]

    found = issues(a, "{{text}}")
    assert [x.severity for x in found] == ["warning"]
    assert issues(i, "{{n}}") == [] and issues(a, "https://example.com") == []
