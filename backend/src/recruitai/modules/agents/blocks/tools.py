"""Action blocks of a flow (ADR 0032): what each ``tool`` node does when the engine reaches it.

Every tool takes only the strings the node's edges delivered and returns a dict of strings, so a
tool step looks to the rest of the engine exactly like any other step. Failures are fixed codes
(never exception text); nothing here logs a query, a URL or a page. Everything that leaves the
machine goes through ``ToolKit``, so tests inject fakes and never touch the network."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway
from recruitai.config import get_settings
from recruitai.core import tool_calls
from recruitai.core import tools as registry
from recruitai.core.email import EmailSender, get_email_sender
from recruitai.core.errors import ValidationFailed
from recruitai.core.telegram import (
    MAX_MESSAGE,
    NOT_SENT,
    Telegram,
    TelegramError,
    get_telegram,
)
from recruitai.core.tools import Call, one_line
from recruitai.modules.agents.blocks.errors import (
    ConnectionLost,
    DeliveryUnknown,
    EmailEmpty,
    MessageEmpty,
    NotConnected,
    RecipientNotAllowed,
    SearchUnavailable,
    ToolFailed,
)
from recruitai.modules.agents.blocks.web import fetch_public_page
from recruitai.modules.agents.connections import service as connections
from recruitai.modules.agents.contacts import service as recipients
from recruitai.modules.agents.flows import repository as flow_repo
from recruitai.modules.agents.flows.models import FlowRun
from recruitai.modules.identity import service as identity  # send_email's language

if TYPE_CHECKING:  # graph imports the catalogue, which imports this module
    from recruitai.modules.agents.flows import graph as g

logger = logging.getLogger(__name__)

MAX_EMAIL_BODY = 5_000
MAX_FAN_OUT = 5  # runs one for_each may start
SEARCH_SYSTEM = (
    "Answer the query with the facts you find on the web, briefly and plainly. "
    "Say so if you find nothing. Never invent a source."
)


Fetcher = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class ToolKit:
    """The outside world a tool may touch."""

    fetch: Fetcher
    mail: EmailSender
    chat: Telegram | None = None  # None: no bot configured


@lru_cache
def default_kit() -> ToolKit:
    return ToolKit(
        fetch=fetch_public_page,
        mail=get_email_sender(get_settings()),
        chat=get_telegram(get_settings()),
    )


# ---- the tools --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ctx(Call):
    """A flow step's call: the run and node too (the effects ledger keys on them) and the toolkit."""

    kit: ToolKit
    run: FlowRun
    node: g.ToolNode


Handler = Callable[[Ctx], Awaitable[dict[str, str]]]


async def _web_search(c: Call) -> dict[str, str]:
    if not c.llm.capabilities("flow_web_search").web_grounding:
        raise SearchUnavailable()
    await c.db.commit()  # nothing held open across the model call
    answer = await c.llm.ground(
        query=c.get("query"),
        system=SEARCH_SYSTEM,
        feature="flow_web_search@1",
        continuation=False,  # a step that starts a search is quota-checked
    )
    return {
        "text": answer.text,
        "sources": "\n".join(f"{s.title}: {s.uri}" for s in answer.sources),
    }


async def _read_page(c: Ctx) -> dict[str, str]:
    await c.db.commit()  # nothing held open (the effect lock) while the page is fetched
    return {"text": await c.kit.fetch(c.get("url").strip())}


async def release_effect(db: AsyncSession, *, run: FlowRun, node: g.ToolNode) -> None:
    await db.rollback()
    await flow_repo.release_effect(db, run_id=run.id, node_id=node.id)
    await db.commit()


def _left_unanswered(exc: Exception) -> bool:
    """A mail provider error caused by a transport failure after the request was sent (a read
    timeout): the outcome is unknown. Anything else (an error status, a connect error, a bug) is a
    definite failure."""
    cause = exc.__cause__
    return isinstance(cause, httpx.TransportError) and not isinstance(cause, NOT_SENT)


async def _send_email(c: Ctx) -> dict[str, str]:
    """One email to an allowed address. Subject is one line; the body is plain text and capped."""
    db, kit, run, node, values = c.db, c.kit, c.run, c.node, c.values
    subject = one_line(values.get("subject"))[:150]
    body = values.get("body", "").strip()[:MAX_EMAIL_BODY]
    if not subject or not body or run.user_id is None:
        raise EmailEmpty()
    try:
        to = recipients.normalize(values.get("to", ""))
    except ValidationFailed as exc:
        raise RecipientNotAllowed() from exc
    verdict = await recipients.may_send(
        db, org_id=run.org_id, user_id=run.user_id, to=to
    )
    if not verdict.allowed:
        raise RecipientNotAllowed()
    settings = get_settings()
    language = await identity.user_language(db, run.user_id)
    sender = await recipients.sender_label(db, run.user_id, language)
    context: dict[str, object] = {
        "language": language,
        "subject": subject,
        "body": body,
        "sender_email": sender,
        "unsubscribe_url": f"{settings.app_base_url}/api/public/email/unsubscribe?t={verdict.unsubscribe_token}",
    }
    await db.commit()  # nothing held open while the mail provider answers
    try:
        await kit.mail.send(to, "flow_message", context)
    except Exception as exc:
        # Unless the request left and no answer came (the provider may have sent it), nothing went
        # out: give the slot back, or a Resume would skip this step and the mail never be sent.
        if _left_unanswered(exc):
            raise DeliveryUnknown() from None
        await release_effect(db, run=run, node=node)
        raise
    return {"status": "sent"}


async def _telegram_send(c: Ctx) -> dict[str, str]:
    """One plain-text message to the chat the run's user linked: the graph names no recipient, so
    there is no way to message anyone else."""
    db, kit, run, node = c.db, c.kit, c.run, c.node
    text = c.get("text").strip()[:MAX_MESSAGE]
    if not text:
        raise MessageEmpty()
    if run.user_id is None or kit.chat is None:
        raise NotConnected()
    org_id, user_id = run.org_id, run.user_id  # a rollback below expires `run`
    chat_id = await connections.active_chat(db, org_id=org_id, user_id=user_id)
    if chat_id is None:
        raise NotConnected()
    await db.commit()  # nothing held open while Telegram answers
    try:
        await kit.chat.send(chat_id, text)
    except TelegramError as exc:
        if exc.unknown:
            raise DeliveryUnknown() from None  # keep the slot: a Resume must not send twice
        await release_effect(db, run=run, node=node)  # refused: a Resume must retry
        if exc.blocked:
            await connections.forget_chat(db, org_id=org_id, user_id=user_id)
            raise ConnectionLost() from None
        raise ToolFailed() from None
    return {"status": "sent"}


# One handler per block of ``catalogue.py``, which registers them (the career tools live in
# their modules' ``tools.py``). ``for_each`` is not here: it starts runs, so the
# engine owns it; ``wait`` is not here either: it parks the run, which is also the engine's job.
HANDLERS: dict[str, Handler] = {
    "web_search": _web_search,
    "read_page": _read_page,
    "send_email": _send_email,
    "telegram_send": _telegram_send,
}


async def run_tool(
    db: AsyncSession,
    llm: LLMGateway,
    kit: ToolKit,
    run: FlowRun,
    node: g.ToolNode,
    values: dict[str, str],
) -> dict[str, str]:
    try:
        tool = registry.get(node.tool)
        registry.handler(node.tool)  # KeyError: a step the engine runs itself
    except KeyError:
        raise ToolFailed() from None
    ctx = Ctx(db, llm, run.org_id, run.user_id, run.job_id, values, kit, run, node)
    try:
        return await tool_calls.invoke(tool, ctx)
    except tool_calls.ToolsUnavailable:
        raise  # it may have run before the line dropped: keep the slot, never twice
    except ToolFailed:
        # the tools service answered "failed" and rolled back, but our claim was committed
        # before the call (ADR 0043): free it, or a Resume would skip a step that never happened
        if tool_calls.remote(tool) and tool.cap is not None and tool.cap.once:
            await release_effect(db, run=run, node=node)
        raise
