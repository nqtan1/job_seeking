"""FastAPI provider for ``LLMGateway``. Bound to the request's tenant so quota and
``ai_calls`` attribution can't be forgotten by a caller. Tests override this dependency
with ``FakeLLMGateway``."""

from collections.abc import AsyncGenerator, Callable
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import BackendCapabilities, LLMGateway
from recruitai.ai.overrides import effective_settings
from recruitai.config import Provider, Settings, get_settings
from recruitai.core.db import get_db
from recruitai.core.tenancy import OrgContext, get_org_context

if TYPE_CHECKING:
    from google import genai
    from openai import AsyncOpenAI

# The provider SDKs (google-genai, openai) cost ~0.7 s of imports: they are loaded on the first
# model call, not at process start, so a cold API instance is ready sooner.


@lru_cache
def _gemini_client() -> "genai.Client":
    from recruitai.ai import gemini

    return gemini.build_client(get_settings())


@lru_cache
def _qwen_client() -> "AsyncOpenAI":
    from recruitai.ai import qwen

    return qwen.build_client(get_settings())


@lru_cache
def _qwen_vl_client() -> "AsyncOpenAI | None":
    from recruitai.ai import qwen

    return qwen.build_vl_client(get_settings())


class _RoutingGateway:
    """Sends each call to the provider config.yaml assigns to its agent (``feature``). A real
    gateway is built on the first call that needs it, so a route that only sometimes needs a
    model (``POST /jobs``) doesn't fail on a missing key or bad URL for requests that never
    call one."""

    def __init__(
        self, settings: Settings, build: Callable[[Provider], LLMGateway]
    ) -> None:
        self._settings = settings
        self._build = build
        self._gateways: dict[Provider, LLMGateway] = {}

    def _for(self, feature: str) -> LLMGateway:
        provider = self._settings.provider_for(feature)
        if provider not in self._gateways:
            self._gateways[provider] = self._build(provider)
        return self._gateways[provider]

    def capabilities(self, feature: str | None = None) -> BackendCapabilities:
        if feature is None:
            raise ValueError(
                "capabilities needs the agent's feature to pick a provider"
            )
        # Provider-level facts: answered without building a client (a missing key or URL
        # must not fail a route that never calls a model).
        if self._settings.provider_for(feature) == "qwen":
            return BackendCapabilities(function_calling=False, web_grounding=False)
        return BackendCapabilities()

    def converse(self, **kwargs: Any) -> AsyncGenerator[Any]:
        return self._for(kwargs["feature"]).converse(**kwargs)

    async def ground(self, **kwargs: Any) -> Any:
        return await self._for(kwargs["feature"]).ground(**kwargs)

    def model_name(
        self, model: Literal["fast", "smart"] = "fast", feature: str | None = None
    ) -> str:
        if feature is None:
            raise ValueError("model_name needs the agent's feature to pick a provider")
        return self._for(feature).model_name(model, feature)

    async def generate(self, **kwargs: Any) -> Any:
        return await self._for(kwargs["feature"]).generate(**kwargs)

    def stream(self, **kwargs: Any) -> AsyncGenerator[str]:
        return self._for(kwargs["feature"]).stream(**kwargs)


def build_llm_gateway(
    settings: Settings, db: AsyncSession, *, org_id: UUID, user_id: UUID
) -> LLMGateway:
    """The tenant-bound gateway (quota and ``ai_calls`` attribution built in). A plain function,
    so worker tasks (the job radar) get the same guarantees as a request."""

    def build(provider: Provider) -> LLMGateway:
        from recruitai.ai import gemini, qwen

        if provider == "qwen":
            return qwen.QwenGateway(
                client=_qwen_client(),
                vl_client=_qwen_vl_client(),
                settings=settings,
                db=db,
                org_id=org_id,
                user_id=user_id,
            )
        return gemini.GeminiGateway(
            client=_gemini_client(),
            settings=settings,
            db=db,
            org_id=org_id,
            user_id=user_id,
        )

    return _RoutingGateway(settings, build)


async def get_llm_gateway(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LLMGateway:
    """Built from the effective settings: ``config.yaml`` plus the admin's model overrides."""
    return build_llm_gateway(
        await effective_settings(settings, db),
        db,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
    )
