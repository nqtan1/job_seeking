"""OpenAI-compatible (Qwen/vLLM) backend (ADR 0015). Dev/self-hosted only — ``Settings``
rejects provider qwen when ``ENV=prod`` (same guard as ``api_key``, see config.py).

``_sanitize_base_url`` is ported verbatim from
``infrastructure/agents/agent_config.py`` (not rewritten — CLAUDE.md porting guide).
"""

import base64
import io
import json
from asyncio import to_thread, wait_for
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal
from uuid import UUID

from openai import APIError, AsyncOpenAI
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FilePart, Part, T, TextPart, provider_errors
from recruitai.ai.usage import CallStats, tracked_call
from recruitai.config import Settings
from recruitai.core.errors import UpstreamUnavailable, ValidationFailed


def _sanitize_base_url(url: str | None) -> str | None:
    if not url:
        return url
    url = url.rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[:-17]
    elif url.endswith("/chat"):
        url = url[:-5]
    url = url.rstrip("/")
    if not url.endswith("/v1") and "/v1/" not in url:
        url = f"{url}/v1"
    return url


def build_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.qwen_api_key or "not-needed-for-a-local-server",
        base_url=_sanitize_base_url(settings.qwen_base_url),
    )


def build_vl_client(settings: Settings) -> AsyncOpenAI | None:
    if not settings.qwen_vl_base_url:
        return None
    return AsyncOpenAI(
        api_key=settings.qwen_vl_api_key or "not-needed-for-a-local-server",
        base_url=_sanitize_base_url(settings.qwen_vl_base_url),
    )


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        raise ValidationFailed("The PDF could not be read.") from exc


async def _text_only(parts: list[Part]) -> tuple[list[Part], bool]:
    """vLLM takes neither PDFs nor text files as content blocks: PDFs (text layer) and text
    files become text, so the cheaper text model serves them (the context window is small).
    Returns the parts and whether any image remains, which needs the vision model."""
    out: list[Part] = []
    has_image = False
    for part in parts:
        if isinstance(part, FilePart) and part.mime_type == "application/pdf":
            text = await to_thread(_pdf_text, part.data)
            if not text:
                raise ValidationFailed(
                    "This PDF has no text layer (scanned). Upload it as a PNG or JPEG instead."
                )
            out.append(TextPart(text))
        elif isinstance(part, FilePart) and part.mime_type == "text/plain":
            out.append(TextPart(part.data.decode("utf-8", errors="replace")))
        else:
            has_image = has_image or isinstance(part, FilePart)
            out.append(part)
    return out, has_image


def _to_openai_content(part: Part) -> dict[str, Any]:
    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    if isinstance(part, FilePart):
        if not part.mime_type.startswith("image/"):
            raise ValueError(
                f"QwenGateway only accepts image FileParts (got {part.mime_type!r}); "
                "extract text from other file types before calling generate()."
            )
        encoded = base64.b64encode(part.data).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{part.mime_type};base64,{encoded}"},
        }
    raise TypeError(f"unknown Part variant: {type(part).__name__}")


def _with_schema(system: str, schema: type[BaseModel]) -> str:
    """vLLM's guided decoding only *constrains* the output to the schema; the model never sees
    the field descriptions (measured: the prompt token count did not change with them). Gemini
    shows ``response_schema`` to the model natively, so for parity we put it in the prompt:
    without it the model didn't know a score was 0-100 or that dates were wanted."""
    compact = json.dumps(
        schema.model_json_schema(), ensure_ascii=False, separators=(",", ":")
    )
    return f"{system}\n\nReturn one JSON object matching this JSON schema:\n{compact}"


class QwenGateway:
    """Same per-request construction as ``GeminiGateway`` — see its docstring."""

    def __init__(
        self,
        *,
        client: AsyncOpenAI,
        settings: Settings,
        db: AsyncSession,
        org_id: UUID,
        user_id: UUID,
        vl_client: AsyncOpenAI | None = None,
    ) -> None:
        self._client = client
        self._vl_client = vl_client or client
        self._settings = settings
        self._db = db
        self._org_id = org_id
        self._user_id = user_id

    def model_name(
        self, model: Literal["fast", "smart"] = "fast", feature: str | None = None
    ) -> str:
        # One text model serves both tiers (images switch to the vision model per call).
        default = self._settings.qwen_model_name or "unset-qwen-model"
        return self._settings.agent_model(feature, default)

    async def _route(
        self, parts: list[Part], feature: str
    ) -> tuple[list[Part], AsyncOpenAI, str]:
        """Pick the server for this input. Done *before* quota is reserved: unreadable input
        (e.g. a scanned PDF) must not cost a call. Images go to the vision model."""
        parts, has_image = await _text_only(parts)
        client, model_name = self._client, self.model_name(feature=feature)
        if has_image:
            client = self._vl_client
            model_name = self._settings.qwen_vl_model_name or model_name
        return parts, client, model_name or "unset-qwen-model"

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
        parts, client, model_name = await self._route(parts, feature)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _with_schema(system, schema)},
            {"role": "user", "content": [_to_openai_content(p) for p in parts]},
        ]
        # Not ``.parse(response_format=schema)``: the SDK's strict transform marks every
        # field required, and a small model then stalls emitting whitespace under vLLM's
        # guided decoding (measured: 200 s timeout vs 10 s with the plain schema).
        response_format: ResponseFormatJSONSchema = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
            },
        }
        async with self._tracked(feature, model_name) as call:
            with provider_errors(APIError):
                completion = await wait_for(
                    client.chat.completions.create(
                        model=model_name,
                        messages=messages,  # type: ignore[arg-type]  # a plain dict list is valid at runtime; mypy wants the SDK's exact TypedDict union
                        response_format=response_format,
                    ),
                    timeout=self._settings.ai_call_timeout_s,
                )
            if completion.usage is not None:
                call.input_tokens = completion.usage.prompt_tokens
                call.output_tokens = completion.usage.completion_tokens
            try:
                return schema.model_validate_json(
                    completion.choices[0].message.content or ""
                )
            except (
                ValidationError,
                IndexError,
            ) as exc:  # IndexError: no choices returned
                raise UpstreamUnavailable(
                    "The AI provider returned an unparseable response.",
                    code="ai_response_invalid",
                ) from exc

    async def stream(
        self,
        *,
        system: str,
        parts: list[Part],
        feature: str,
        model: Literal["fast", "smart"] = "fast",
    ) -> AsyncGenerator[str]:
        parts, client, model_name = await self._route(parts, feature)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": [_to_openai_content(p) for p in parts]},
        ]
        timeout = self._settings.ai_call_timeout_s
        async with self._tracked(feature, model_name) as call:
            with provider_errors(APIError):
                completion = await wait_for(
                    client.chat.completions.create(  # type: ignore[call-overload]  # plain-dict messages are valid at runtime; the SDK wants its exact TypedDict union
                        model=model_name,
                        messages=messages,
                        stream=True,
                        stream_options={"include_usage": True},
                    ),
                    timeout=timeout,
                )
                iterator = completion.__aiter__()
                while True:
                    try:
                        # Idle timeout: each chunk must arrive in time; the whole reply may take longer.
                        chunk = await wait_for(iterator.__anext__(), timeout=timeout)
                    except StopAsyncIteration:
                        break
                    if chunk.usage is not None:
                        call.input_tokens = chunk.usage.prompt_tokens
                        call.output_tokens = chunk.usage.completion_tokens
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
