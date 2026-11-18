"""The tracker tool of the career pack (ADR 0039). Its daily cap is the flow engine's (``cap``)."""

from datetime import UTC, datetime
from typing import Any

from recruitai.core import tools
from recruitai.core.tools import Call, Cap, Tool, one_line, register, register_reader
from recruitai.modules.applications import service as applications
from recruitai.modules.applications.schemas import ApplicationIn


def tracker_args(values: dict[str, str]) -> dict[str, str]:
    """The tracker's inputs as its handler uses them: what the chat's card shows (PA-11)."""
    title = one_line(values.get("title"))[:200]
    out = {
        # an offer without an employer is filed under its title
        "company": (one_line(values.get("company")) or title)[:200],
        "title": title,
        "notes": "\n".join(
            x
            for x in (values.get("url", "").strip(), values.get("notes", "").strip())
            if x
        )[:5000],
        "status": "applied"
        if values.get("status", "").strip().lower() == "applied"
        else "to_apply",
    }
    return {k: v for k, v in out.items() if v}


async def _add_to_tracker(c: Call) -> dict[str, str]:
    """The job the run or chat is about, when there is one, is linked (its company and title win)."""
    args = tracker_args(c.values)
    card = await applications.create_application(
        c.db,
        org_id=c.org_id,
        data=ApplicationIn(
            job_id=c.job_id,
            status="applied" if args["status"] == "applied" else "to_apply",
            location=None,
            company_name=args.get("company"),
            job_title=args.get("title"),
            notes=args.get("notes"),
        ),
    )
    return {"status": f"added:{card.id}"}


register(
    Tool(
        "add_to_tracker",
        "career",
        (
            ("company", True),
            ("title", False),
            ("url", False),
            ("notes", False),
            ("status", False),  # "applied" or else "to apply"
        ),
        ("status",),
        effect="write",
        cap=Cap(50),
        chat=True,
    ),
    _add_to_tracker,
)


SITUATION_CHARS = 600
_ORDER = (
    "to_apply",
    "applied",
    "in_review",
    "interview",
    "offer",
    "rejected",
    "ghosted",
)


def _card(company: str, title: str | None) -> str:
    return one_line(f"{title} @ {company}" if title else company)[:60]


async def _last_run(c: Call) -> str | None:
    run = await tools.read("last_run", c)
    if run is None:
        return None
    when = run.get("finished_at")
    days = ""
    if when:
        n = (datetime.now(UTC) - when).days
        days = ", today" if n == 0 else f", {n} days ago"
    return f"Last automation: {one_line(run['name'])[:60]} ({run['status']}{days})"


async def _situation(c: Call) -> dict[str, Any] | None:
    """Short plain lines on where the user stands (ADR 0042); None when there is nothing."""
    s = await applications.situation(c.db, org_id=c.org_id)
    lines = []
    if s is not None:
        counts = s["counts"]
        stages = [f"{counts[k]} {k.replace('_', ' ')}" for k in _ORDER if k in counts]
        lines.append("Tracker: " + ", ".join(stages))
        lines += [
            f"Interview {at.date().isoformat()}: {_card(co, t)}"
            for co, t, at in s["upcoming"]
        ]
        lines += [f"No reply {d} days: {_card(co, t)}" for co, t, d in s["stale"]]
    if run := await _last_run(c):
        lines.append(run)
    if not lines:
        return None
    text = "\n".join(lines)
    return {"text": text[:SITUATION_CHARS], "truncated": len(text) > SITUATION_CHARS}


register_reader("situation", _situation)
