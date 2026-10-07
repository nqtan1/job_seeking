"""ai/gateway.py (P1-11): the LLMGateway protocol + FakeLLMGateway."""

import pytest
from pydantic import BaseModel

from recruitai.ai.gateway import FakeLLMGateway, LLMGateway, TextPart


class Greeting(BaseModel):
    text: str


async def summarize_via_gateway(gateway: LLMGateway, name: str) -> Greeting:
    """A stand-in for a real service — the point is that it only knows the protocol,
    never a concrete backend."""
    return await gateway.generate(
        schema=Greeting,
        system="You write short greetings.",
        parts=[TextPart(text=f"Greet {name}")],
        feature="test_greeting",
    )


async def test_dummy_service_gets_the_queued_fixture():
    gateway = FakeLLMGateway()
    gateway.queue("test_greeting", Greeting(text="hi Ada"))

    result = await summarize_via_gateway(gateway, "Ada")

    assert result == Greeting(text="hi Ada")
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call.feature == "test_greeting"
    assert call.model == "fast"
    assert call.parts == [TextPart(text="Greet Ada")]


async def test_missing_fixture_raises_loudly():
    gateway = FakeLLMGateway()
    with pytest.raises(AssertionError, match="no queued response"):
        await summarize_via_gateway(gateway, "Ada")


async def test_wrong_schema_fixture_raises_type_error():
    class OtherSchema(BaseModel):
        n: int

    gateway = FakeLLMGateway()
    gateway.queue("test_greeting", OtherSchema(n=1))

    with pytest.raises(TypeError):
        await summarize_via_gateway(gateway, "Ada")


async def test_queue_is_fifo_per_feature():
    gateway = FakeLLMGateway()
    gateway.queue("test_greeting", Greeting(text="first"))
    gateway.queue("test_greeting", Greeting(text="second"))

    first = await summarize_via_gateway(gateway, "x")
    second = await summarize_via_gateway(gateway, "x")

    assert (first.text, second.text) == ("first", "second")
