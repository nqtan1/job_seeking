"""The profile tool of the career pack (ADR 0039). Only the summary and the skills leave: never the
contact details or the references (identity-free, like the coach's profile)."""

from recruitai.core.tools import Call, Tool, register
from recruitai.modules.candidates import service as candidates


async def _profile_read(c: Call) -> dict[str, str]:
    data = (await candidates.get_profile(c.db, org_id=c.org_id)).data
    return {
        "summary": data.get("summary") or "",
        "skills": ", ".join(s["name"] for s in data.get("skills") or []),
    }


register(
    Tool(
        "profile_read",
        "career",
        (("start", False),),
        ("summary", "skills"),
        chat=True,
        page="/profile",
    ),
    _profile_read,
)
