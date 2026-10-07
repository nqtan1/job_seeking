import pytest

from recruitai.ai.gateway import FakeLLMGateway


@pytest.fixture
def fake_llm() -> FakeLLMGateway:
    return FakeLLMGateway()
