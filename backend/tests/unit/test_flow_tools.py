"""Action blocks (ADR 0032): the page reader refuses the private network, and the graph knows tools."""

import pytest

import recruitai.packs  # noqa: F401  every pack registers its tools
from recruitai.core import tools as registry
from recruitai.modules.agents.blocks.errors import ToolFailed
from recruitai.modules.agents.blocks.web import MAX_TEXT, fetch_public_page, page_text
from recruitai.modules.agents.flows import graph as g
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
    with pytest.raises(ToolFailed):  # UrlNotAllowed, or a failed lookup: never a fetch
        await fetch_public_page(url)


def test_page_text_drops_scripts_and_keeps_the_words():
    html = "<html><head><title>x</title></head><body><script>evil()</script><h1>Dev</h1><p>Python &amp; SQL</p></body></html>"
    assert page_text(html) == "Dev\nPython & SQL"
    assert len(page_text("<p>" + "a" * 50_000)) == MAX_TEXT


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


def test_every_tool_has_a_handler_unless_the_engine_owns_it():
    """Adding a tool is one spec and one handler, in any pack: the two cannot drift apart."""
    for t in registry.all().values():
        engine_owned = t.starts_runs or t.pauses
        assert (t.id in registry._HANDLERS) != engine_owned, t.id


def test_every_pack_flag_is_a_setting():
    """A misspelled flag would turn a flow save or a run into a 500 (getattr on Settings)."""
    from recruitai.config import Settings

    for t in registry.all().values():
        assert t.flag is None or t.flag in Settings.model_fields, t.id


async def test_a_remote_step_that_failed_frees_its_run_once_slot_but_not_when_the_line_dropped(
    monkeypatch,
):
    """ADR 0043: the claim is committed before the call, so a "failed" answer (the service rolled
    back) frees it for a Resume; an unknown outcome keeps it (never twice)."""
    from types import SimpleNamespace

    from recruitai.core import tool_calls
    from recruitai.modules.agents.blocks import tools as blocks

    released: list[str] = []

    async def release(db, *, run, node):
        released.append(node.id)

    monkeypatch.setattr(blocks, "release_effect", release)
    monkeypatch.setattr(tool_calls, "remote", lambda tool: True)
    run = SimpleNamespace(org_id=None, user_id=None, job_id=None)
    for error, freed in (
        (ToolFailed(code="not_found"), ["n1"]),
        (tool_calls.ToolsUnavailable(), []),
    ):

        async def fail(tool, call, error=error):
            raise error

        monkeypatch.setattr(tool_calls, "invoke", fail)
        released.clear()
        for tool, node_id in (
            ("save_note", "n1"),
            ("job_lookup", "n2"),
        ):  # capped once / no cap
            with pytest.raises(ToolFailed):
                await blocks.run_tool(None, None, None, run, SimpleNamespace(id=node_id, tool=tool), {})  # fmt: skip
        assert released == freed
