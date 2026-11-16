"""The tracker tool of the career pack (ADR 0039). Its daily cap is the flow engine's (``cap``)."""

from recruitai.core.tools import Call, Cap, Tool, one_line, register
from recruitai.modules.applications import service as applications
from recruitai.modules.applications.schemas import ApplicationIn


async def _add_to_tracker(c: Call) -> dict[str, str]:
    title = one_line(c.get("title"))
    card = await applications.create_application(
        c.db,
        org_id=c.org_id,
        data=ApplicationIn(
            job_id=None,
            location=None,
            # an offer without an employer is filed under its title
            company_name=(one_line(c.get("company")) or title)[:200] or None,
            job_title=title[:200] or None,
            notes="\n".join(
                x for x in (c.get("url").strip(), c.get("notes").strip()) if x
            )[:5000]
            or None,
        ),
    )
    return {"status": f"added:{card.id}"}


register(
    Tool(
        "add_to_tracker",
        "career",
        (("company", True), ("title", False), ("url", False), ("notes", False)),
        ("status",),
        effect="write",
        cap=Cap(50),
    ),
    _add_to_tracker,
)
