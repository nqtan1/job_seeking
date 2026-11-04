"""Action blocks of a flow (ADR 0032): what each ``tool`` node does when the engine reaches it.

Every tool takes only the strings the node's edges delivered and returns a dict of strings, so a
tool step looks to the rest of the engine exactly like any other step. Failures are fixed codes
(never exception text); nothing here logs a query, a URL or a page. Everything that leaves the
machine goes through ``ToolKit``, so tests inject fakes and never touch the network."""

import asyncio
import hashlib
import ipaddress
import logging
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from html.parser import HTMLParser
from typing import ClassVar, NamedTuple
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway
from recruitai.config import get_settings
from recruitai.core.email import EmailSender, get_email_sender
from recruitai.core.errors import AppError, ValidationFailed
from recruitai.modules.agents import flow_repository as flow_repo
from recruitai.modules.agents import graph as g
from recruitai.modules.agents import recipients
from recruitai.modules.agents.models import FlowRun
from recruitai.modules.applications import service as applications
from recruitai.modules.applications.schemas import ApplicationIn
from recruitai.modules.identity import service as identity
from recruitai.modules.jobs import service as jobs
from recruitai.modules.jobs.providers.base import JobProvider

logger = logging.getLogger(__name__)

MAX_PAGE_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
FETCH_TIMEOUT_S = 10.0
MAX_TEXT = 20_000
MAX_EMAIL_BODY = 5_000
SEARCH_RESULTS = 5
NEW_OFFER_WINDOW = 20  # offers looked at to find one the user has not seen
SEEN_FOR = timedelta(days=90)
SEARCH_SYSTEM = (
    "Answer the query with the facts you find on the web, briefly and plainly. "
    "Say so if you find nothing. Never invent a source."
)


class ToolFailed(AppError):
    status_code = 502
    code = "tool_failed"
    default_detail = "This step could not finish."


class UrlNotAllowed(ToolFailed):
    code = "url_not_allowed"
    default_detail = "That address cannot be opened."


class NoJob(ToolFailed):
    code = "no_job"
    default_detail = "This step needs a job: pick one when you run it."


class RecipientNotAllowed(ToolFailed):
    code = "recipient_not_allowed"
    default_detail = "That address is not one you may email."


class EmailEmpty(ToolFailed):
    code = "email_empty"
    default_detail = "The email has no subject or no text."


class SearchUnavailable(ToolFailed):
    code = "search_unavailable"
    default_detail = "Web search is not available right now."


# Tools with an outside effect run at most once per run and step (the ``flow_effects`` ledger), and
# a user can cause only so many per day. ``kind`` is the ledger's label.
class Cap(NamedTuple):
    user: int  # per user per day
    everyone: int | None = None  # all users together per day
    once: bool = True  # False: repeatable (counted, but a resumed step just runs again)


EFFECT_CAPS: dict[str, Cap] = {
    "add_to_tracker": Cap(50),
    "send_email": Cap(20, 500),
    "read_page": Cap(200, once=False),  # not a free proxy for scanning
}

Fetcher = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class ToolKit:
    """The outside world a tool may touch."""

    fetch: Fetcher
    jobs: JobProvider
    mail: EmailSender


# ---- read_page: a public https page, as text, with the network closed to everything else ----


async def _public_address(host: str) -> str:
    """One public IP for the host. A name that resolves to a private, loopback, link-local or
    metadata address is refused, so a page address can never reach our own network."""
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise UrlNotAllowed()  # a bare IP is never needed for a public page
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, 443, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise ToolFailed() from exc
    addresses = [ipaddress.ip_address(i[4][0]) for i in infos]
    if not addresses or not all(a.is_global for a in addresses):
        raise UrlNotAllowed()
    return str(addresses[0])


class _Text(HTMLParser):
    SKIP: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "template", "svg", "head"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        self._skip += tag in self.SKIP
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        self._skip = max(0, self._skip - (tag in self.SKIP))

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def page_text(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()[:MAX_TEXT]


async def fetch_public_page(url: str) -> str:
    """GET a public https page and return its text. https on 443 only, every hop (redirects too)
    re-checked, the connection pinned to the checked IP, 1 MiB and 10 s at most."""
    async with asyncio.timeout(FETCH_TIMEOUT_S):
        async with httpx.AsyncClient(follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                parts = urlsplit(url)
                host = parts.hostname or ""
                if (
                    parts.scheme != "https"
                    or parts.port not in (None, 443)
                    or parts.username
                    or not host
                ):
                    raise UrlNotAllowed()
                ip = await _public_address(host)
                pinned = parts._replace(netloc=f"[{ip}]" if ":" in ip else ip).geturl()
                async with (
                    client.stream(
                        "GET",
                        pinned,
                        headers={
                            "Host": host,
                            "User-Agent": "RecruitAI-automation",
                            "Accept-Encoding": "identity",  # no compression: the size cap is real
                        },
                        extensions={"sni_hostname": host},
                    ) as response
                ):
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code >= 400:
                        raise ToolFailed()
                    if (
                        response.headers.get("content-encoding", "identity")
                        != "identity"
                    ):
                        raise ToolFailed()
                    kind = (
                        response.headers.get("content-type", "").split(";")[0].strip()
                    )
                    if kind not in ("text/html", "text/plain", "application/xhtml+xml"):
                        raise ToolFailed()
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_PAGE_BYTES:
                            break
                    text = body[:MAX_PAGE_BYTES].decode(
                        response.encoding or "utf-8", errors="replace"
                    )
                    return page_text(text) if kind != "text/plain" else text[:MAX_TEXT]
    raise ToolFailed()  # too many redirects


@lru_cache
def default_kit() -> ToolKit:
    from recruitai.config import get_settings
    from recruitai.modules.jobs.providers.factory import france_travail_provider

    return ToolKit(
        fetch=fetch_public_page,
        jobs=france_travail_provider(),
        mail=get_email_sender(get_settings()),
    )


# ---- the tools --------------------------------------------------------------------------------


def _one_line(value: str | None) -> str:
    return " ".join((value or "").split())


async def run_tool(
    db: AsyncSession,
    llm: LLMGateway,
    kit: ToolKit,
    run: FlowRun,
    node: g.ToolNode,
    values: dict[str, str],
) -> dict[str, str]:
    org_id, job_id = run.org_id, run.job_id
    v = values.get
    match node.tool:
        case "web_search":
            if not llm.capabilities("flow_web_search").web_grounding:
                raise SearchUnavailable()
            await db.commit()  # nothing held open across the model call
            answer = await llm.ground(
                query=v("query", ""),
                system=SEARCH_SYSTEM,
                feature="flow_web_search@1",
                continuation=False,  # a step that starts a search is quota-checked
            )
            return {
                "text": answer.text,
                "sources": "\n".join(f"{s.title}: {s.uri}" for s in answer.sources),
            }
        case "job_search":
            found = await jobs.search(
                db,
                kit.jobs,
                query=v("query", "") or None,
                department=v("department") or None,
                limit=SEARCH_RESULTS,
            )
            lines = [
                f"{_one_line(r.title)} · {_one_line(r.company)} · "
                f"{_one_line(r.location)} · {r.url}"
                for r in found.results[:SEARCH_RESULTS]
            ]
            return {"text": "\n".join(lines), "count": str(len(lines))}
        case "new_offer":
            return await _new_offer(db, kit, run, node, values)
        case "read_page":
            return {"text": await kit.fetch(v("url", "").strip())}
        case "job_lookup":
            if job_id is None:
                raise NoJob()
            job = await jobs.get_job(db, org_id=org_id, job_id=job_id)
            data = job.data
            return {
                "title": job.title,
                "company": job.company or "",
                "place": jobs.place_of(data) or "",
                "description": str(data.get("job_description_text") or "")[:MAX_TEXT],
                "url": str(data.get("url") or ""),
            }
        case "add_to_tracker":
            card = await applications.create_application(
                db,
                org_id=org_id,
                data=ApplicationIn(
                    job_id=None,
                    location=None,
                    company_name=_one_line(v("company"))[:200],
                    job_title=_one_line(v("title"))[:200] or None,
                    notes="\n".join(
                        x for x in (v("url", "").strip(), v("notes", "").strip()) if x
                    )[:5000]
                    or None,
                ),
            )
            return {"status": f"added:{card.id}"}
        case "send_email":
            return await _send_email(db, kit, run, node, values)
    raise ToolFailed()


async def _new_offer(
    db: AsyncSession,
    kit: ToolKit,
    run: FlowRun,
    node: g.ToolNode,
    values: dict[str, str],
) -> dict[str, str]:
    """The first offer of the search that this user was not handed before; it is marked as handed
    out in the same step, so tomorrow's run gets the next one. Nothing new: every field is empty
    (a Condition on ``url`` then ends the flow quietly). A resumed step gets its own offer back."""
    if run.user_id is None:
        raise ToolFailed()
    user_id, run_id = run.user_id, run.id
    found = await jobs.search(
        db,
        kit.jobs,
        query=values.get("query") or None,
        department=values.get("department") or None,
        limit=NEW_OFFER_WINDOW,
    )
    offers = {
        hashlib.sha256(r.url.encode()).hexdigest(): r for r in found.results if r.url
    }
    await flow_repo.forget_old_offers(
        db, user_id=user_id, cutoff=datetime.now(UTC) - SEEN_FOR
    )
    seen = await flow_repo.seen_hashes(db, user_id=user_id, hashes=list(offers))
    picked = await flow_repo.offer_picked_by(db, run_id=run_id, node_id=node.id)
    left = len(offers) - len(seen)
    if picked is None:
        for digest in offers.keys() - seen:  # a resumed step already has its offer
            if await flow_repo.take_offer(
                db,
                org_id=run.org_id,
                user_id=user_id,
                run_id=run_id,
                node_id=node.id,
                url_hash=digest,
            ):
                picked, left = digest, left - 1
                break
    await db.commit()
    offer = offers.get(picked or "")
    if offer is None:
        return dict.fromkeys(g.TOOLS["new_offer"][1], "") | {"remaining": "0"}
    return {
        "title": _one_line(offer.title),
        "company": _one_line(offer.company),
        "place": _one_line(offer.location),
        "url": offer.url,
        "remaining": str(max(left, 0)),
    }


async def release_effect(db: AsyncSession, *, run: FlowRun, node: g.ToolNode) -> None:
    await db.rollback()
    await flow_repo.release_effect(db, run_id=run.id, node_id=node.id)
    await db.commit()


async def _send_email(
    db: AsyncSession,
    kit: ToolKit,
    run: FlowRun,
    node: g.ToolNode,
    values: dict[str, str],
) -> dict[str, str]:
    """One email to an allowed address. Subject is one line; the body is plain text and capped."""
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
    except Exception:
        # The provider refused it, so nothing went out: give the slot back, or a Resume would
        # skip this step as "already done" and the mail would never be sent.
        await release_effect(db, run=run, node=node)
        raise
    return {"status": "sent"}
