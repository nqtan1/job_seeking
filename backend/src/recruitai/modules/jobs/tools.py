"""The job tools of the career pack (ADR 0039): search offers, find new ones, read the chosen job.

The job board is the one France Travail provider of ``providers.factory``, looked up at call time
so tests and the e2e worker replace it there. Failures are fixed codes, never exception text."""

import json
from typing import Any

from recruitai.ai.gateway import QuotaExceeded
from recruitai.core.tools import (
    Call,
    Cap,
    NoJob,
    Tool,
    one_line,
    register,
    register_reader,
)
from recruitai.modules.jobs import service as jobs
from recruitai.modules.jobs.providers import factory

SEARCH_RESULTS = 5
MAX_FAN_OUT = 5  # offers one find_offers hands on (== agents' for_each fan-out)
FIND_WINDOW = 20  # offers looked at to find new ones
MAX_TEXT = 20_000


async def _job_search(c: Call) -> dict[str, str]:
    found = await jobs.search(
        c.db,
        factory.france_travail_provider(),
        query=c.get("query") or None,
        department=c.get("department") or None,
        limit=SEARCH_RESULTS,
    )
    lines = [
        f"{one_line(r.title)} · {one_line(r.company)} · "
        f"{one_line(r.location)} · {r.url}"
        for r in found.results[:SEARCH_RESULTS]
    ]
    return {"text": "\n".join(lines), "count": str(len(lines))}


async def _job_lookup(c: Call) -> dict[str, str]:
    if c.job_id is None:
        raise NoJob()
    job = await jobs.get_job(c.db, org_id=c.org_id, job_id=c.job_id)
    data = job.data
    return {
        "title": job.title,
        "company": job.company or "",
        "place": jobs.place_of(data) or "",
        "description": str(data.get("job_description_text") or "")[:MAX_TEXT],
        "url": str(data.get("url") or ""),
    }


async def _search_terms(
    c: Call, text: str, department: str | None
) -> tuple[str | None, str | None, str | None]:
    """What to search for, from what the user typed: a sentence such as "AI engineer in Paris"
    becomes keywords + a department + a contract type, as on the Jobs page. If the sentence
    cannot be read, the text itself is searched."""
    if not text:
        return None, department, None
    await c.db.commit()  # nothing held open across the model call
    try:
        parsed = await jobs.parse_query(c.llm, text=text)
    except QuotaExceeded:
        raise
    except Exception:  # noqa: BLE001  (an unreadable sentence must not stop the search)
        return text, department, None
    return parsed.query or text, department or parsed.department, parsed.contract_type


async def _find_offers(c: Call) -> dict[str, str]:
    """New offers of a search: those this account has not saved as a Job yet (the same memory as
    Radar and the Jobs page). Each of up to MAX_FAN_OUT is fetched in full and saved, so every
    later step reads the real offer. An offer that cannot be fetched is skipped (it comes back
    next time) and never costs the others."""
    db, org_id, provider = c.db, c.org_id, factory.france_travail_provider()
    query, department, contract = await _search_terms(
        c, c.get("query").strip(), c.get("department") or None
    )
    found = await jobs.search(
        db,
        provider,
        query=query,
        department=department,
        contract_type=contract,
        limit=FIND_WINDOW,
    )
    known = await jobs.known_external_ids(
        db,
        org_id=org_id,
        source=provider.name,
        external_ids=[r.id for r in found.results],
    )
    fresh = [r for r in found.results if r.id not in known and r.url]
    items: list[dict[str, str]] = []
    for r in fresh[:MAX_FAN_OUT]:
        try:
            posting = await jobs.save_new_search_result(
                db, provider, org_id=org_id, external_id=r.id
            )
        except Exception:  # noqa: BLE001  (one unreadable offer must not cost the others)
            await db.rollback()
            continue
        if posting is not None:
            items.append(
                {
                    "job_id": str(posting.id),
                    "title": one_line(r.title),
                    "company": one_line(r.company),
                    "place": one_line(r.location),
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


register(
    Tool(
        "job_search",
        "career",
        (("query", True), ("department", False)),
        ("text", "count"),
    ),
    _job_search,
)
# new offers of a search (not yet saved as Jobs), saved with their full text; ``items`` is JSON,
# one object per offer (job_id, title, company, place, url) for for_each
register(
    Tool(
        "find_offers",
        "career",
        (("query", True), ("department", False)),
        ("items", "text", "count", "remaining"),
        cap=Cap(30, once=False),  # searches a day: each fetches up to 5 full offers
        ai_uses=1,  # reads the search sentence
        chat=True,
    ),
    _find_offers,
)
# reads the run's chosen job; "start" is an optional link so it can hang off the Input step
register(
    Tool(
        "job_lookup",
        "career",
        (("start", False),),
        ("title", "company", "place", "description", "url"),
        needs_job=True,
        chat=True,
        untrusted=True,  # a job ad is written by the employer
    ),
    _job_lookup,
)


async def _job(c: Call) -> dict[str, Any]:
    """A helper's "job" source, and the 404 check before a run: NotFound across orgs."""
    if c.job_id is None:
        raise NoJob()
    return (await jobs.get_job(c.db, org_id=c.org_id, job_id=c.job_id)).data


register_reader("job", _job)
