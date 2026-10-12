"""``LLMGateway`` (ADR 0009, ARCHITECTURE.md §4.5): the only way any service calls a model.

``Part`` is ours, not the vendor's — ``ai/gemini.py`` (P1-12) translates it into
``google.genai.types.Part``, ``ai/qwen.py`` (P1-12b) into an OpenAI-style content block.
Keeping the protocol vendor-neutral is the whole point of the gateway (ADR 0009's "why":
business code stays independent of the SDK).

Calls are stateless: no conversation history is kept here (ADR 0009, ADR 0016) — a caller
that needs multi-turn context (coach, P2-23c) passes the full history explicitly every time,
as part of ``parts``.
"""

from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel

from recruitai.core.errors import AppError, UpstreamUnavailable

T = TypeVar("T", bound=BaseModel)


class QuotaExceeded(AppError):
    """Shared by every real backend (ai/gemini.py, ai/qwen.py) — the daily per-user AI
    quota (ADR 0009 item 14: cost protection must be structural, not per-backend)."""

    status_code = 429
    code = "quota_exceeded"
    default_detail = "Daily AI usage limit reached. Please try again tomorrow."


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class FilePart:
    data: bytes
    mime_type: str


Part = TextPart | FilePart


@dataclass(frozen=True)
class BackendCapabilities:
    """What a backend can do for the coach: the loop offers tools only to a backend that can
    call them, and says so to the user when web research is missing (never a silent failure)."""

    function_calling: bool = True
    web_grounding: bool = True


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (an object)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    name: str
    result: dict[str, Any]


# One conversation, vendor-neutral, for ``converse``. The history is rebuilt by the caller each
# turn (stateless, ADR 0009/0016); within a turn the loop appends what the model asked for.
@dataclass(frozen=True)
class UserTurn:
    text: str


@dataclass(frozen=True)
class ToolCallTurn:
    """The model's tool request. ``raw`` is the vendor's own message, replayed verbatim (some
    models need their signed "thought" parts returned unchanged)."""

    calls: list[ToolCall]
    raw: Any


@dataclass(frozen=True)
class ToolResultTurn:
    results: list[ToolResult]


Turn = UserTurn | ToolCallTurn | ToolResultTurn


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCalls:
    calls: list[ToolCall]
    raw: Any


ChatEvent = TextDelta | ToolCalls


@dataclass(frozen=True)
class Source:
    title: str
    uri: str
    domain: str | None = None


@dataclass(frozen=True)
class GroundedAnswer:
    """A web-grounded answer: Google's Search Suggestion markup must be shown unmodified with it."""

    text: str
    sources: list[Source]
    queries: list[str]
    suggestions_html: str | None = None


class LLMGateway(Protocol):
    def capabilities(self, feature: str | None = None) -> BackendCapabilities:
        """From settings alone: answering must not build a provider client."""
        ...

    def converse(
        self,
        *,
        system: str,
        turns: list[Turn],
        tools: list[ToolSpec],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
        allow_tools: bool = True,
        continuation: bool = False,
    ) -> AsyncGenerator[ChatEvent]:
        """One model call of the coach's tool loop, streamed. ``allow_tools=False`` forces a
        plain answer. ``continuation`` marks a follow-up call of the same user turn: it is
        metered in ``ai_calls`` but not refused by the daily quota mid-turn."""
        ...

    async def ground(self, *, query: str, system: str, feature: str) -> GroundedAnswer:
        """One web-grounded call (Google Search). Only for backends with ``web_grounding``."""
        ...

    def model_name(
        self, model: Literal["fast", "smart"] = "fast", feature: str | None = None
    ) -> str:
        """The concrete model a tier resolves to, for services that store it (``fit_analyses``)."""
        ...

    async def generate(
        self,
        *,
        schema: type[T],
        system: str,
        parts: list[Part],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
    ) -> T: ...

    def stream(
        self,
        *,
        system: str,
        parts: list[Part],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
    ) -> AsyncGenerator[str]:
        """Free text, token by token (the coach chat). Same quota and ``ai_calls`` rules as
        ``generate``; stateless too: a multi-turn caller passes the whole history in ``parts``.
        Errors before the first chunk raise as usual; no retries once streaming has begun."""
        ...


@contextmanager
def provider_errors(*sdk_errors: type[BaseException]) -> Iterator[None]:
    """Turn a provider's failures into the one clean error clients see: a timeout becomes
    ``ai_timeout`` and any of the SDK's own errors becomes ``ai_unavailable``. The message is
    fixed (SDK text could echo request content) and the cause stays chained for debugging."""
    try:
        yield
    except TimeoutError as exc:
        raise UpstreamUnavailable(
            "The AI provider timed out.", code="ai_timeout"
        ) from exc
    except sdk_errors as exc:
        raise UpstreamUnavailable(
            "The AI provider is unavailable.", code="ai_unavailable"
        ) from exc


async def generate_retrying_invalid[M: BaseModel](
    llm: LLMGateway,
    *,
    schema: type[M],
    system: str,
    parts: list[Part],
    feature: str,
    model: Literal["fast", "smart"] = "fast",
) -> M:
    """``generate`` that retries once on unparseable output (ARCHITECTURE.md §4.5), then lets
    the same clean 503 through. Malformed output is usually a one-off sampling slip; a timeout
    is not retried (it would double the wait)."""
    try:
        return await llm.generate(
            schema=schema, system=system, parts=parts, feature=feature, model=model
        )
    except UpstreamUnavailable as exc:
        if exc.code != "ai_response_invalid":
            raise
        return await llm.generate(
            schema=schema, system=system, parts=parts, feature=feature, model=model
        )


@dataclass
class RecordedCall:
    schema: type[BaseModel] | None  # None for ``stream`` calls
    system: str
    parts: list[Part]
    feature: str
    model: Literal["fast", "smart"]


@dataclass
class FakeLLMGateway:
    """Test double (ADR 0009: "tests use a FakeLLMGateway that returns fixtures"). Queue a
    response per feature with ``queue()``; ``generate()`` pops the next one, or raises if
    none was queued — a test that forgets to queue a fixture fails loudly, not silently."""

    _fixtures: dict[str, list[BaseModel]] = field(default_factory=dict)
    _streams: dict[str, list[tuple[list[str], Exception | None]]] = field(
        default_factory=dict
    )
    calls: list[RecordedCall] = field(default_factory=list)
    caps: BackendCapabilities = field(default_factory=BackendCapabilities)
    _turns: dict[str, list[tuple[list[ChatEvent], Exception | None]]] = field(
        default_factory=dict
    )
    _grounded: list[GroundedAnswer | Exception] = field(default_factory=list)
    converse_calls: list[dict[str, Any]] = field(default_factory=list)
    ground_calls: list[str] = field(default_factory=list)

    def capabilities(self, feature: str | None = None) -> BackendCapabilities:
        return self.caps

    def queue_turn(
        self, feature: str, events: list[ChatEvent], *, error: Exception | None = None
    ) -> None:
        """The events the next ``converse()`` for ``feature`` yields. Without one, it falls
        back to a queued ``queue_stream`` (text only), so plain replies need no change."""
        self._turns.setdefault(feature, []).append((events, error))

    def queue_ground(self, answer: GroundedAnswer | Exception) -> None:
        self._grounded.append(answer)

    async def ground(self, *, query: str, system: str, feature: str) -> GroundedAnswer:
        self.ground_calls.append(query)
        if not self._grounded:
            raise AssertionError("FakeLLMGateway has no queued grounded answer")
        answer = self._grounded.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def converse(
        self,
        *,
        system: str,
        turns: list[Turn],
        tools: list[ToolSpec],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
        allow_tools: bool = True,
        continuation: bool = False,
    ) -> AsyncGenerator[ChatEvent]:
        self.converse_calls.append(
            {
                "turns": turns,
                "tools": tools,
                "allow_tools": allow_tools,
                "system": system,
            }
        )
        queued = self._turns.get(feature)
        if queued:
            events, error = queued.pop(0)
            for event in events:
                yield event
            if error is not None:
                raise error
            return
        text_parts = [t.text for t in turns if isinstance(t, UserTurn)]
        async for chunk in self.stream(
            system=system,
            parts=[TextPart("\n".join(text_parts))],
            feature=feature,
            model=model,
        ):
            yield TextDelta(chunk)

    def model_name(
        self, model: Literal["fast", "smart"] = "fast", feature: str | None = None
    ) -> str:
        return f"fake-{model}"

    def queue(self, feature: str, response: BaseModel) -> None:
        self._fixtures.setdefault(feature, []).append(response)

    def queue_stream(
        self, feature: str, chunks: list[str], *, error: Exception | None = None
    ) -> None:
        """The chunks the next ``stream()`` for ``feature`` yields; ``error`` is raised after
        them, to test a failure in the middle of a reply."""
        self._streams.setdefault(feature, []).append((chunks, error))

    async def stream(
        self,
        *,
        system: str,
        parts: list[Part],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
    ) -> AsyncGenerator[str]:
        self.calls.append(
            RecordedCall(
                schema=None, system=system, parts=parts, feature=feature, model=model
            )
        )
        queued = self._streams.get(feature)
        if not queued:
            raise AssertionError(
                f"FakeLLMGateway has no queued stream for feature={feature!r}"
            )
        chunks, error = queued.pop(0)
        for chunk in chunks:
            yield chunk
        if error is not None:
            raise error

    async def generate(
        self,
        *,
        schema: type[T],
        system: str,
        parts: list[Part],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
    ) -> T:
        self.calls.append(
            RecordedCall(
                schema=schema, system=system, parts=parts, feature=feature, model=model
            )
        )
        queued = self._fixtures.get(feature)
        if not queued:
            raise AssertionError(
                f"FakeLLMGateway has no queued response for feature={feature!r}"
            )
        response: Any = queued.pop(0)
        if not isinstance(response, schema):
            raise TypeError(
                f"queued response for feature={feature!r} is a {type(response).__name__}, "
                f"not the requested {schema.__name__}"
            )
        return response
