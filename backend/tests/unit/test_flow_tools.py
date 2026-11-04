"""Action blocks (ADR 0032): the page reader refuses the private network, and the graph knows tools."""

import re

import pytest

from recruitai.modules.agents import graph as g
from recruitai.modules.agents import tools
from tests.unit.test_flow_graph import ids


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",  # not https
        "https://example.com:8443/",  # not 443
        "https://user:pw@example.com/",  # credentials in the address
        "https://127.0.0.1/",  # a bare IP
        "https://[::1]/",
        "https://169.254.169.254/latest/meta-data",  # the cloud metadata address
        "https://localhost/",  # a name that resolves to loopback
        "ftp://example.com/",
        "https:///nohost",
    ],
)
async def test_the_page_reader_never_reaches_a_private_or_odd_address(url):
    with pytest.raises(
        tools.ToolFailed
    ):  # UrlNotAllowed, or a failed lookup: never a fetch
        await tools.fetch_public_page(url)


def test_page_text_drops_scripts_and_keeps_the_words():
    html = "<html><head><title>x</title></head><body><script>evil()</script><h1>Dev</h1><p>Python &amp; SQL</p></body></html>"
    assert tools.page_text(html) == "Dev\nPython & SQL"
    assert len(tools.page_text("<p>" + "a" * 50_000)) == tools.MAX_TEXT


def test_tool_blocks_have_fixed_inputs_and_outputs_and_a_job_lookup_needs_no_wire():
    i, t, o = ids(3)
    graph = g.Graph.model_validate(
        {
            "nodes": [
                {"type": "input", "id": i, "fields": [{"name": "q", "label": "Q"}]},
                {"type": "tool", "id": t, "tool": "job_lookup"},
                {"type": "output", "id": o, "fields": [{"name": "r", "label": "R"}]},
            ],
            "edges": [
                {
                    "id": ids(1)[0],
                    "from": {"node": t, "port": "out"},
                    "to": o,
                    "map": [{"input": "r", "value": "{{title}}"}],
                }
            ],
        }
    )
    assert [x for x in g.validate(graph, {}) if x.severity == "error"] == []
    with pytest.raises(ValueError):  # a tool that does not exist cannot be saved
        g.ToolNode.model_validate({"id": t, "tool": "run_shell"})


def test_the_web_editor_knows_exactly_the_action_blocks_the_server_has():
    from tests.unit.test_flow_graph import LIMITS

    web = LIMITS.read_text()
    block = web[web.index("export const TOOL_IO") : web.index("} as const satisfies")]
    for kind, (inputs, outputs) in g.TOOLS.items():
        part = block[block.index(f"{kind}:") :].split("},", 1)[0]
        names = {n for n, _ in inputs} | set(outputs)
        assert names <= set(re.findall(r"'([a-z_]+)'", part)), kind
        assert len(re.findall(r"\['", part.split("out:")[0])) == len(inputs), kind
    assert set(re.findall(r"^\s{2}([a-z_]+): \{", block, re.MULTILINE)) == set(g.TOOLS)
