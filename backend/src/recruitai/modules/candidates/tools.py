"""The profile tool of the career pack (ADR 0039). Only the summary and the skills leave: never the
contact details or the references (identity-free, like the coach's profile)."""

from typing import Any

from recruitai.core.tools import Call, Tool, register, register_reader
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
        mcp=True,
    ),
    _profile_read,
)


async def _profile(c: Call) -> dict[str, Any]:
    """A helper's "profile" source: the whole profile (the helper drops the identity keys)."""
    return (await candidates.require_profile(c.db, org_id=c.org_id)).data


register_reader("profile", _profile)


async def _remember(c: Call) -> dict[str, str]:
    added = await candidates.add_fact(c.db, org_id=c.org_id, text=c.get("text"))
    return {"status": "saved" if added else "already saved"}


register(
    Tool(
        "remember",
        "career",
        (("text", True),),
        ("status",),
        effect="write",
        chat=True,
        chat_only=True,  # no page text a flow read goes into memory
    ),
    _remember,
)


async def _memory(c: Call) -> dict[str, str] | None:
    """A helper's "memory" source. The coach fences it as untrusted, not this reader."""
    facts = await candidates.get_memory(c.db, org_id=c.org_id)
    return {"text": "\n".join(f"- {f['text']}" for f in facts)} if facts else None


register_reader("memory", _memory)
