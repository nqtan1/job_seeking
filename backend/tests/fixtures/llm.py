"""Placeholder fake LLM. Replaced by the real ``FakeLLMGateway`` in P1-11; tests must
never make a real LLM call."""

from typing import Any

import pytest


class FakeLLMGateway:
    def __init__(self) -> None:
        self.responses: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    async def generate(self, *, schema: Any, feature: str, **kwargs: Any) -> Any:
        self.calls.append({"schema": schema, "feature": feature, **kwargs})
        if not self.responses:
            raise AssertionError("FakeLLMGateway has no queued response")
        return self.responses.pop(0)


@pytest.fixture
def fake_llm() -> FakeLLMGateway:
    return FakeLLMGateway()
