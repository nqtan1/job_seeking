"""HTTP for the people a flow may email (ADR 0032). The two public pages (confirm, unsubscribe) are
the only unauthenticated routes of the feature: a tiny HTML page with a button, because mail
scanners open links and a plain GET must never change anything."""

from datetime import datetime
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings, get_settings
from recruitai.core.db import get_db
from recruitai.core.email import EmailSender, get_email_sender
from recruitai.core.errors import (
    Conflict,
    NotFound,
    Unauthorized,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.ratelimit import limit_public, limit_sensitive
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.agents.base import Strict
from recruitai.modules.agents.contacts import service
from recruitai.modules.agents.contacts.models import EmailRecipient
from recruitai.modules.agents.deps import require_enabled

router = APIRouter(prefix="/api/v1", tags=["email"])
# Public like the radar link (/api/public/...): the one-time token in the link is the credential.
public_router = APIRouter(prefix="/api/public/email", tags=["email"])
authed = [Depends(require_enabled)]


class RecipientIn(Strict):
    email: str = Field(max_length=254)


class RecipientOut(BaseModel):
    id: UUID
    email: str
    status: str
    created_at: datetime


def get_sender(settings: Annotated[Settings, Depends(get_settings)]) -> EmailSender:
    return get_email_sender(settings)


def _out(r: EmailRecipient) -> RecipientOut:
    return RecipientOut(
        id=r.id, email=r.email, status=r.status, created_at=r.created_at
    )


@router.get(
    "/email-recipients",
    response_model=list[RecipientOut],
    dependencies=authed,
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_recipients(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RecipientOut]:
    return [_out(r) for r in await service.list_recipients(db, ctx)]


@router.post(
    "/email-recipients",
    response_model=RecipientOut,
    status_code=201,
    dependencies=[*authed, Depends(limit_sensitive)],
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed, Conflict),
)
async def add_recipient(
    body: RecipientIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    sender: Annotated[EmailSender, Depends(get_sender)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecipientOut:
    """Adds an address and emails it a confirmation link. Nothing can be sent to it until its owner confirms."""
    return _out(
        await service.add_recipient(
            db, ctx, body.email, sender=sender, settings=settings
        )
    )


@router.delete(
    "/email-recipients/{recipient_id}",
    status_code=204,
    dependencies=authed,
    responses=problem_responses(Unauthorized, NotFound),
)
async def remove_recipient(
    recipient_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.remove_recipient(db, ctx, recipient_id)
    return Response(status_code=204)


# ---- public pages -----------------------------------------------------------------------------

_PAGE = (
    "<!doctype html><html lang=en><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>RecruitAI</title><body style='font-family:system-ui;max-width:32rem;"
    "margin:4rem auto;padding:0 1rem'><h1 style='font-size:1.25rem'>{title}</h1>"
    "<p>{text}</p>{form}</body></html>"
)


def _page(
    title: str, text: str, action: str | None = None, token: str = ""
) -> HTMLResponse:
    form = (
        f"<form method=post action='{action}?t={quote(token, safe='')}'>"
        f"<button style='padding:.6rem 1rem;font-size:1rem'>{title}</button></form>"
        if action
        else ""
    )
    return HTMLResponse(_PAGE.format(title=title, text=text, form=form))


# Own buckets: a flood on the confirm page must never lock people out of unsubscribing.
public = [Depends(limit_public("email_confirm", limit=120))]
public_stop = [Depends(limit_public("email_unsubscribe", limit=600))]


@public_router.get("/confirm", response_class=HTMLResponse, dependencies=public)
async def confirm_page(t: Annotated[str, Query(max_length=100)]) -> HTMLResponse:
    return _page(
        "Confirm this address",
        "Someone added your address in RecruitAI so their automations can email you.",
        "/api/public/email/confirm",
        t,
    )


@public_router.post("/confirm", response_class=HTMLResponse, dependencies=public)
async def confirm(
    t: Annotated[str, Query(max_length=100)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HTMLResponse:
    ok = await service.confirm(db, t)
    return _page(
        "Confirmed" if ok else "This link is not valid",
        "You may now receive their messages. Every message has an unsubscribe link."
        if ok
        else "It was already used, or it expired.",
    )


@public_router.get(
    "/unsubscribe", response_class=HTMLResponse, dependencies=public_stop
)
async def unsubscribe_page(t: Annotated[str, Query(max_length=100)]) -> HTMLResponse:
    return _page(
        "Stop these emails",
        "You will not receive any more emails from RecruitAI automations.",
        "/api/public/email/unsubscribe",
        t,
    )


@public_router.post(
    "/unsubscribe", response_class=HTMLResponse, dependencies=public_stop
)
async def unsubscribe(
    t: Annotated[str, Query(max_length=100)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HTMLResponse:
    """Also the target of one-click unsubscribe from mail apps (RFC 8058)."""
    ok = await service.unsubscribe(db, t)
    return _page(
        "Done" if ok else "This link is not valid",
        "You will not receive these emails any more."
        if ok
        else "It may already be used.",
    )
