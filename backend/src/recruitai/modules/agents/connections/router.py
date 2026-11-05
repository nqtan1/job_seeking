"""HTTP for connections (ADR 0036). The web app asks "check" while the person is in Telegram, so
linking finishes in seconds; the worker polls too, for the case where the page was closed."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings, get_settings
from recruitai.core.db import get_db
from recruitai.core.errors import Conflict, NotFound, Unauthorized, problem_responses
from recruitai.core.ratelimit import rate_limit
from recruitai.core.telegram import Telegram, get_telegram
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.agents.connections import service
from recruitai.modules.agents.deps import require_enabled

router = APIRouter(
    prefix="/api/v1/connections",
    tags=["connections"],
    dependencies=[Depends(require_enabled)],
)
limit_connections = rate_limit("connections", limit=30)


class ConnectionOut(BaseModel):
    provider: str
    status: str
    connected_at: datetime | None


class ConnectionsOut(BaseModel):
    items: list[ConnectionOut]
    telegram_available: bool  # the platform has a bot configured


class LinkOut(BaseModel):
    url: str
    expires_at: datetime


def bot(settings: Annotated[Settings, Depends(get_settings)]) -> Telegram | None:
    return get_telegram(settings)


async def _all(
    db: AsyncSession, ctx: OrgContext, tg: Telegram | None
) -> ConnectionsOut:
    return ConnectionsOut(
        items=[
            ConnectionOut(
                provider=c.provider, status=c.status, connected_at=c.connected_at
            )
            for c in await service.list_connections(db, ctx)
        ],
        telegram_available=tg is not None,
    )


@router.get(
    "",
    response_model=ConnectionsOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_connections(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tg: Annotated[Telegram | None, Depends(bot)],
) -> ConnectionsOut:
    return await _all(db, ctx, tg)


@router.post(
    "/telegram/link",
    response_model=LinkOut,
    dependencies=[Depends(limit_connections)],
    responses=problem_responses(Unauthorized, NotFound, Conflict, service.NotAvailable),
)
async def link_telegram(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tg: Annotated[Telegram | None, Depends(bot)],
) -> LinkOut:
    link = await service.start_telegram_link(db, ctx, tg, now=datetime.now(UTC))
    return LinkOut(url=link.url, expires_at=link.expires_at)


@router.post(
    "/telegram/check",
    response_model=ConnectionsOut,
    dependencies=[Depends(limit_connections)],
    responses=problem_responses(Unauthorized, NotFound),
)
async def check_telegram(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    tg: Annotated[Telegram | None, Depends(bot)],
) -> ConnectionsOut:
    """Look for the code the person just sent the bot (anyone's: the answer is only their own list)."""
    if tg is not None:
        await service.poll_telegram(db, tg, now=datetime.now(UTC))
    return await _all(db, ctx, tg)


@router.delete(
    "/telegram",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def disconnect_telegram(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.disconnect(db, ctx, "telegram")
    return Response(status_code=204)
