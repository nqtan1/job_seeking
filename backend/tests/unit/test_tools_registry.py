"""The tool registry (ADR 0039): an id is registered once (handlers: test_flow_tools)."""

import pytest

import recruitai.packs  # noqa: F401  every pack registers its tools
from recruitai.core import tools


def test_a_tool_id_is_registered_once():
    with pytest.raises(RuntimeError):
        tools.register(tools.get("web_search"), None)
