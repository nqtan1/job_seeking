"""Action blocks of a flow (ADR 0032): what each ``tool`` node does when the engine reaches it.

Every tool takes only the strings the node's edges delivered and returns a dict of strings, so a
tool step looks to the rest of the engine exactly like any other step. Failures are fixed codes
(never exception text); nothing here logs a query, a URL or a page. Everything that leaves the
machine goes through ``ToolKit``, so tests inject fakes and never touch the network."""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway, QuotaExceeded
from recruitai.config import get_settings
from recruitai.core.email import EmailSender, get_email_sender
from recruitai.core.errors import ValidationFailed
from recruitai.core.telegram import (
    MAX_MESSAGE,
    NOT_SENT,
    Telegram,
    TelegramError,
    get_telegram,
)
from recruitai.modules.agents.blocks.errors import (
    ConnectionLost,
    DeliveryUnknown,
    EmailEmpty,
    MessageEmpty,
    NoJob,
    NotConnected,
    RecipientNotAllowed,
    SearchUnavailable,
    ToolFailed,
)
from recruitai.modules.agents.blocks.web import MAX_TEXT, fetch_public_page
from recruitai.modules.agents.connections import service as connections
from recruitai.modules.agents.contacts import service as recipients
from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import repository as flow_repo
from recruitai.modules.agents.flows.models import FlowRun
from recruitai.modules.applications import service as applications
from recruitai.modules.applications.schemas import ApplicationIn
from recruitai.modules.identity import service as identity
from recruitai.modules.jobs import service as jobs
from recruitai.modules.jobs.providers.base import JobProvider
from recruitai.modules.matching import schemas as matching_schemas
from recruitai.modules.matching import service as matching

logger = logging.getLogger(__name__)

MAX_EMAIL_BODY = 5_000
SEARCH_RESULTS = 5
MAX_FAN_OUT = 5  # items one step may hand on, and runs one for_each may start
FIND_WINDOW = 20  # offers looked at to find new ones
SEARCH_SYSTEM = (
    "Answer the query with the facts you find on the web, briefly and plainly. "
    "Say so if you find nothing. Never invent a source."
)


Fetcher = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class ToolKit:
    """The outside world a tool may touch."""

    fetch: Fetcher
    jobs: JobProvider
    mail: EmailSender
    chat: Telegram | None = None  # None: no bot configured


@lru_cache
def default_kit() -> ToolKit:
    from recruitai.config import get_settings
    from recruitai.modules.jobs.providers.factory import france_travail_provider

    return ToolKit(
        fetch=fetch_public_page,
        jobs=france_travail_provider(),
        mail=get_email_sender(get_settings()),
        chat=get_telegram(get_settings()),
    )


# ---- the tools --------------------------------------------------------------------------------


def _one_line(value: str | None) -> str:
    return " ".join((value or "").split())


@dataclass(frozen=True)
class Ctx:
    """Everything one block step may use: its run, its node, the values its edges delivered."""

    db: AsyncSession
    llm: LLMGateway
    kit: ToolKit
    run: FlowRun
    node: g.ToolNode
    values: dict[str, str]

    def get(self, name: str, default: str = "") -> str:
        return self.values.get(name, default)


Handler = Callable[[Ctx], Awaitable[dict[str, str]]]


async def _web_search(c: Ctx) -> dict[str, str]:
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


async def _job_search(c: Ctx) -> dict[str, str]:
    found = await jobs.search(
        c.db,
        c.kit.jobs,
        query=c.get("query") or None,
        department=c.get("department") or None,
        limit=SEARCH_RESULTS,
    )
    lines = [
        f"{_one_line(r.title)} · {_one_line(r.company)} · "
        f"{_one_line(r.location)} · {r.url}"
        for r in found.results[:SEARCH_RESULTS]
    ]
    return {"text": "\n".join(lines), "count": str(len(lines))}


async def _read_page(c: Ctx) -> dict[str, str]:
    await c.db.commit()  # nothing held open (the effect lock) while the page is fetched
    return {"text": await c.kit.fetch(c.get("url").strip())}


async def _job_lookup(c: Ctx) -> dict[str, str]:
    if c.run.job_id is None:
        raise NoJob()
    job = await jobs.get_job(c.db, org_id=c.run.org_id, job_id=c.run.job_id)
    data = job.data
    return {
        "title": job.title,
        "company": job.company or "",
        "place": jobs.place_of(data) or "",
        "description": str(data.get("job_description_text") or "")[:MAX_TEXT],
        "url": str(data.get("url") or ""),
    }


async def _add_to_tracker(c: Ctx) -> dict[str, str]:
    title = _one_line(c.get("title"))
    card = await applications.create_application(
        c.db,
        org_id=c.run.org_id,
        data=ApplicationIn(
            job_id=None,
            location=None,
            # an offer without an employer is filed under its title
            company_name=(_one_line(c.get("company")) or title)[:200] or None,
            job_title=title[:200] or None,
            notes="\n".join(
                x for x in (c.get("url").strip(), c.get("notes").strip()) if x
            )[:5000]
            or None,
        ),
    )
    return {"status": f"added:{card.id}"}


async def _search_terms(
    db: AsyncSession, llm: LLMGateway, text: str, department: str | None
) -> tuple[str | None, str | None, str | None]:
    """What to search for, from what the user typed: a sentence such as "AI engineer in Paris"
    becomes keywords + a department + a contract type, as on the Jobs page. If the sentence
    cannot be read, the text itself is searched."""
    if not text:
        return None, department, None
    await db.commit()  # nothing held open across the model call
    try:
        parsed = await jobs.parse_query(llm, text=text)
    except QuotaExceeded:
        raise
    except Exception:  # noqa: BLE001  (an unreadable sentence must not stop the search)
        return text, department, None
    return parsed.query or text, department or parsed.department, parsed.contract_type


async def _find_offers(c: Ctx) -> dict[str, str]:
    """New offers of a search: those this account has not saved as a Job yet (the same memory as
    Radar and the Jobs page). Each of up to MAX_FAN_OUT is fetched in full and saved, so every
    later step reads the real offer. An offer that cannot be fetched is skipped (it comes back
    next time) and never costs the others."""
    db, llm, kit, values = c.db, c.llm, c.kit, c.values
    org_id = c.run.org_id  # a rollback below expires `run`: read what is needed first
    query, department, contract = await _search_terms(
        db, llm, values.get("query", "").strip(), values.get("department") or None
    )
    found = await jobs.search(
        db,
        kit.jobs,
        query=query,
        department=department,
        contract_type=contract,
        limit=FIND_WINDOW,
    )
    known = await jobs.known_external_ids(
        db,
        org_id=org_id,
        source=kit.jobs.name,
        external_ids=[r.id for r in found.results],
    )
    fresh = [r for r in found.results if r.id not in known and r.url]
    items: list[dict[str, str]] = []
    for r in fresh[:MAX_FAN_OUT]:
        try:
            posting = await jobs.save_new_search_result(
                db, kit.jobs, org_id=org_id, external_id=r.id
            )
        except Exception:  # noqa: BLE001  (one unreadable offer must not cost the others)
            await db.rollback()
            continue
        if posting is not None:
            items.append(
                {
                    "job_id": str(posting.id),
                    "title": _one_line(r.title),
                    "company": _one_line(r.company),
                    "place": _one_line(r.location),
                    "url": r.url,
                }
            )
    return {
        "items": json.dumps(items, ensure_ascii=False),
        "text": "\n".join(
            f"{i['title']} · {i['company']} · {i['place']} · {i['url']}" for i in items
        ),
        "count": str(len(items)),
        "remaining": str(max(len(fresh) - len(items), 0)),
    }


async def _fit_check(c: Ctx) -> dict[str, str]:
    """The app's own fit analysis (tested prompts, one persona per employer type) of the run's
    job against the account's profile. An existing analysis of the job is reused."""
    db, llm, run = c.db, c.llm, c.run
    if run.job_id is None or run.user_id is None:
        raise NoJob()
    employer = c.get("employer", "").strip().lower()
    company_type: matching_schemas.CompanyType = (
        "startup"
        if employer == "startup"
        else "phd"
        if employer == "phd"
        else "corporate"
    )
    language = await identity.user_language(db, run.user_id)
    await db.commit()  # nothing held open across the model call
    row = await matching.latest_or_analyze(
        db,
        llm,
        org_id=run.org_id,
        job_id=run.job_id,
        company_type=company_type,
        language=language,
    )

    def bullets(key: str) -> str:
        return "\n".join(f"- {x}" for x in row.data.get(key) or [])

    return {
        "score": str(row.score),
        "verdict": row.verdict,
        "strengths": bullets("strengths"),
        "gaps": bullets("gaps"),
        "missing": bullets("key_missing_requirements"),
        "reasons": bullets("reasons"),
    }


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
    subject = _one_line(values.get("subject"))[:150]
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


# One handler per block of ``blocks.BLOCKS``. ``for_each`` is not here: it starts runs, so the
# engine owns it; ``wait`` is not here either: it parks the run, which is also the engine's job.
HANDLERS: dict[str, Handler] = {
    "web_search": _web_search,
    "job_search": _job_search,
    "find_offers": _find_offers,
    "fit_check": _fit_check,
    "read_page": _read_page,
    "job_lookup": _job_lookup,
    "add_to_tracker": _add_to_tracker,
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
    handler = HANDLERS.get(node.tool)
    if handler is None:
        raise ToolFailed()
    return await handler(Ctx(db, llm, kit, run, node, values))
