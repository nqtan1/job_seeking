"""``build_llm_gateway`` (behind ``get_llm_gateway``) is lazy: resolving it builds no client; the first model call does."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from recruitai.ai import dependencies
from recruitai.config import AGENTS, Settings


async def test_a_broken_llm_config_only_fails_when_a_model_call_is_made(monkeypatch):
    def broken_client() -> None:
        raise RuntimeError("client-built")

    monkeypatch.setattr(dependencies, "_qwen_client", broken_client)
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        env="local",
        database_url="postgresql+psycopg://u:p@localhost/x_test",
        firebase_project_id="demo",
        agents={a: {"provider": "qwen"} for a in AGENTS},
    )
    ctx = MagicMock(org_id=uuid4(), user_id=uuid4())

    gateway = dependencies.build_llm_gateway(  # must not raise
        settings, MagicMock(), org_id=ctx.org_id, user_id=ctx.user_id
    )

    with pytest.raises(RuntimeError, match="client-built"):
        await gateway.generate(schema=None, system="s", parts=[], feature="fit")
