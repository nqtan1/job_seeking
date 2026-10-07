"""_sanitize_base_url (P1-12b): ported verbatim from
infrastructure/agents/agent_config.py — same cases the legacy code handled."""

import pytest

from recruitai.ai.qwen import _sanitize_base_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (None, None),
        ("", ""),
        ("http://localhost:8000", "http://localhost:8000/v1"),
        ("http://localhost:8000/", "http://localhost:8000/v1"),
        ("http://localhost:8000/v1", "http://localhost:8000/v1"),
        ("http://localhost:8000/v1/", "http://localhost:8000/v1"),
        ("http://localhost:8000/chat/completions", "http://localhost:8000/v1"),
        ("http://localhost:8000/v1/chat/completions", "http://localhost:8000/v1"),
        ("http://localhost:8000/chat", "http://localhost:8000/v1"),
        ("http://localhost:8000/v1/chat", "http://localhost:8000/v1"),
        ("http://localhost:8000/v1/beta", "http://localhost:8000/v1/beta"),
    ],
)
def test_sanitize_base_url(given: str | None, expected: str | None):
    assert _sanitize_base_url(given) == expected
