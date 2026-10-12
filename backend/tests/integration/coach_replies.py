"""Test helper: the coach service yields events; most tests only want the reply's text."""

from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway
from recruitai.config import Settings, get_settings
from recruitai.modules.coach import service


def with_tools() -> Settings:
    return get_settings().model_copy(update={"coach_job_focus": True})


async def events(
    db: AsyncSession,
    llm: Any,
    *,
    org_id: UUID,
    conversation_id: UUID,
    content: str,
    settings: Settings | None = None,
) -> AsyncGenerator[tuple[str, dict[str, Any]]]:
    async with aclosing(
        service.stream_reply(
            db,
            llm,
            settings or get_settings(),
            org_id=org_id,
            conversation_id=conversation_id,
            content=content,
        )
    ) as stream:
        async for event in stream:
            yield event


async def replies(
    db: AsyncSession, llm: LLMGateway, **kwargs: Any
) -> AsyncGenerator[str]:
    """The reply's text chunks (``token`` events)."""
    async for name, data in events(db, llm, **kwargs):
        if name == "token":
            yield data["text"]
