"""Connections (ADR 0036): linking a user's Telegram to the platform bot and sending to it.

Linking proves ownership: the person gets a one-time code (stored hashed, 15 minutes) and sends it
to the platform bot; whoever does so owns that chat. A flow can then message only that chat."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import AppError, Conflict, NotFound
from recruitai.core.telegram import Telegram, TelegramError
from recruitai.core.tenancy import OrgContext
from recruitai.modules.agents.connections import repository as repo
from recruitai.modules.agents.connections.models import Connection
from recruitai.modules.identity import service as identity

LINK_VALID = timedelta(minutes=15)
CODE_PREFIX = "/start "

# Plain English: the bot does not know its readers' language yet.
WELCOME = "Connected to {who}. Your automations can now message you here. Not you? Send /stop."
STOPPED = "Disconnected."


def _who(email: str | None) -> str:
    """Name the account without giving it away (the sign-in provider verified the address)."""
    if not email or "@" not in email:
        return "a RecruitAI account"
    name, _, host = email.partition("@")
    return f"the RecruitAI account {name[0]}***@{host}"


class NotAvailable(AppError):
    status_code = 503
    code = "connector_unavailable"
    default_detail = "This connection is not available right now."


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@dataclass(frozen=True)
class LinkStart:
    url: str
    expires_at: datetime


async def list_connections(db: AsyncSession, ctx: OrgContext) -> list[Connection]:
    return await repo.list_for_user(db, org_id=ctx.org_id, user_id=ctx.user_id)


async def start_telegram_link(
    db: AsyncSession, ctx: OrgContext, tg: Telegram | None, *, now: datetime
) -> LinkStart:
    if tg is None:
        raise NotAvailable()
    row = await repo.get(
        db, org_id=ctx.org_id, user_id=ctx.user_id, provider="telegram"
    )
    if row is not None and row.status == "active":
        raise Conflict("Telegram is already connected. Disconnect it first.")
    code = secrets.token_urlsafe(24)
    expires = now + LINK_VALID
    if row is None:
        row = await repo.add(
            db,
            Connection(org_id=ctx.org_id, user_id=ctx.user_id, provider="telegram"),
        )
    row.link_hash, row.link_expires_at = _hash(code), expires
    await db.commit()
    return LinkStart(url=f"https://t.me/{tg.username}?start={code}", expires_at=expires)


async def poll_telegram(db: AsyncSession, tg: Telegram, *, now: datetime) -> int:
    """Read what people sent the bot and finish the links. Returns how many were linked."""
    linked = 0
    try:
        updates = await tg.updates()
    except TelegramError:
        return 0
    for u in updates:
        if (
            u.text.strip() == "/stop"
        ):  # whoever was linked by mistake can undo it; says nothing else
            if await repo.delete_by_chat(db, provider="telegram", chat_id=u.chat_id):
                await db.commit()
                try:
                    await tg.send(u.chat_id, STOPPED)
                except TelegramError:
                    pass
            continue
        if not u.text.startswith(CODE_PREFIX):
            continue
        row = await repo.pending_by_hash(
            db,
            provider="telegram",
            link_hash=_hash(u.text[len(CODE_PREFIX) :].strip()),
            now=now,
        )
        if row is None or await repo.chat_is_linked(
            db, provider="telegram", chat_id=u.chat_id
        ):
            continue  # an unknown, expired or already used code, or a chat linked elsewhere
        # read before changing the row: a query would autoflush the change outside the try below
        who = _who(await identity.verified_email_of(db, user_id=row.user_id))
        row.status, row.chat_id, row.connected_at = "active", u.chat_id, now
        row.link_hash = row.link_expires_at = None  # the code works once
        try:
            await db.commit()
        except IntegrityError:  # a parallel poll linked this chat first
            await db.rollback()
            continue
        linked += 1
        try:
            await tg.send(u.chat_id, WELCOME.format(who=who))
        except TelegramError:
            pass  # linked all the same
    return linked


async def disconnect(db: AsyncSession, ctx: OrgContext, provider: str) -> None:
    if not await repo.delete_for_user(
        db, org_id=ctx.org_id, user_id=ctx.user_id, provider=provider
    ):
        raise NotFound("Not found.")
    await db.commit()


async def active_chat(db: AsyncSession, *, org_id: UUID, user_id: UUID) -> int | None:
    row = await repo.get(db, org_id=org_id, user_id=user_id, provider="telegram")
    return row.chat_id if row is not None and row.status == "active" else None


async def forget_chat(db: AsyncSession, *, org_id: UUID, user_id: UUID) -> None:
    """The person blocked the bot: the link is useless, so drop it (they can link again)."""
    await repo.delete_for_user(db, org_id=org_id, user_id=user_id, provider="telegram")
    await db.commit()
