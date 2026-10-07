"""Real Gemini backend (ADR 0009): Vertex AI in prod, API key in dev. Structured output via
``google-genai``'s ``response_schema``. Cost protection is structural — the daily quota is
checked inside ``generate()`` itself, never left to callers to remember (item 14 of the
2026-09-28 review).

Prompt versioning note: the ``LLMGateway`` protocol (P1-11, matching ADR 0009 exactly) has
no separate ``prompt_version`` parameter, but ``ai_calls.prompt_version`` is required. This
backend treats the ``feature`` argument itself as the versioned identifier a prompt module
exports (ADR 0009's own example: ``PROMPT_VERSION = "cv_extract@3"``) — the full string is
stored as ``prompt_version``, and the part before ``@`` is stored as the shorter, groupable
``feature``. No caller exists yet (P2 builds the first one); worth confirming this
convention against the real prompt modules when they land.
"""

import asyncio
import random
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Literal
from uuid import UUID

import httpx
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FilePart, Part, T, TextPart, provider_errors
from recruitai.ai.usage import CallStats, tracked_call
from recruitai.config import Settings
from recruitai.core.errors import UpstreamUnavailable

_RETRYABLE_CODES = frozenset({429, 500, 502, 503, 504})
# What this SDK (and its HTTP layer) raises: all of it becomes a clean ``ai_unavailable``.
_SDK_ERRORS = (ClientError, ServerError, httpx.HTTPError)


def build_client(settings: Settings) -> genai.Client:
    if settings.gemini_auth == "vertex":
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location,
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _model_name(
    settings: Settings, model: Literal["fast", "smart"], feature: str | None = None
) -> str:
    tier = settings.gemini_flash_lite if model == "fast" else settings.gemini_flash
    return settings.agent_model(feature, tier)


def _to_genai_part(part: Part) -> types.Part:
    if isinstance(part, TextPart):
        return types.Part.from_text(text=part.text)
    if isinstance(part, FilePart):
        return types.Part.from_bytes(data=part.data, mime_type=part.mime_type)
    raise TypeError(f"unknown Part variant: {type(part).__name__}")


class GeminiGateway:
    """Bound to one request's tenant context at construction time — the ``LLMGateway``
    protocol itself carries no ``org_id``/``user_id``, so quota and ``ai_calls`` attribution
    live here, not in ``generate()``'s parameters."""

    def __init__(
        self,
        *,
        client: genai.Client,
        settings: Settings,
        db: AsyncSession,
        org_id: UUID,
        user_id: UUID,
    ) -> None:
        self._client = client
        self._settings = settings
        self._db = db
        self._org_id = org_id
        self._user_id = user_id

    def model_name(
        self, model: Literal["fast", "smart"] = "fast", feature: str | None = None
    ) -> str:
        return _model_name(self._settings, model, feature)

    async def _call_with_retries(
        self,
        *,
        model_name: str,
        contents: list[types.Part],
        config: types.GenerateContentConfig,
    ) -> types.GenerateContentResponse:
        delay = 1.0
        for attempt in range(self._settings.ai_max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,  # type: ignore[arg-type]  # list[Part] is a valid member of the SDK's contents union; mypy's list invariance rejects it anyway
                        config=config,
                    ),
                    timeout=self._settings.ai_call_timeout_s,
                )
            except (ClientError, ServerError, httpx.TransportError) as exc:
                # A dropped connection is as transient as a 503; both back off and retry.
                retryable = (
                    isinstance(exc, httpx.TransportError)
                    or exc.code in _RETRYABLE_CODES
                )
                if not retryable or attempt == self._settings.ai_max_retries:
                    raise
                await asyncio.sleep(delay + random.uniform(0, 0.1))
                delay *= 2
        raise AssertionError("unreachable")  # the loop always returns or raises

    def _tracked(
        self, feature: str, model_name: str
    ) -> AbstractAsyncContextManager[CallStats]:
        return tracked_call(
            self._db,
            org_id=self._org_id,
            user_id=self._user_id,
            feature=feature,
            model=model_name,
            quota=self._settings.ai_daily_quota_per_user,
        )

    async def generate(
        self,
        *,
        schema: type[T],
        system: str,
        parts: list[Part],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
    ) -> T:
        model_name = _model_name(self._settings, model, feature)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
        )
        async with self._tracked(feature, model_name) as call:
            with provider_errors(*_SDK_ERRORS):
                response = await self._call_with_retries(
                    model_name=model_name,
                    contents=[_to_genai_part(p) for p in parts],
                    config=config,
                )
            usage = response.usage_metadata
            if usage is not None:
                call.input_tokens = usage.prompt_token_count or 0
                call.output_tokens = usage.candidates_token_count or 0
            parsed = response.parsed
            if not isinstance(parsed, schema):
                # The model failed to honor response_schema: an upstream failure, not a
                # caller bug (a bare exception would surface as an unhandled 500).
                raise UpstreamUnavailable(
                    "The AI provider returned an unparseable response.",
                    code="ai_response_invalid",
                )
            return parsed

    async def stream(
        self,
        *,
        system: str,
        parts: list[Part],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
    ) -> AsyncGenerator[str]:
        model_name = _model_name(self._settings, model, feature)
        timeout = self._settings.ai_call_timeout_s
        async with self._tracked(feature, model_name) as call:
            with provider_errors(*_SDK_ERRORS):
                chunks = await asyncio.wait_for(
                    self._client.aio.models.generate_content_stream(
                        model=model_name,
                        contents=[_to_genai_part(p) for p in parts],  # type: ignore[arg-type]  # list invariance, as in _call_with_retries
                        config=types.GenerateContentConfig(system_instruction=system),
                    ),
                    timeout=timeout,
                )
                iterator = chunks.__aiter__()
                while True:
                    try:
                        # Idle timeout: each chunk must arrive in time; the whole reply may take longer.
                        chunk = await asyncio.wait_for(
                            iterator.__anext__(), timeout=timeout
                        )
                    except StopAsyncIteration:
                        break
                    if chunk.usage_metadata is not None:
                        call.input_tokens = chunk.usage_metadata.prompt_token_count or 0
                        call.output_tokens = (
                            chunk.usage_metadata.candidates_token_count or 0
                        )
                    if chunk.text:
                        yield chunk.text
