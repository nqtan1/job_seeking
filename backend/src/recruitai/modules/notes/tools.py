"""The web & research pack (ADR 0039): ``save_note`` and ``summarise``, registered in core.tools."""

from pydantic import ValidationError

from recruitai.core.language import Language
from recruitai.core.tools import Call, Cap, Tool, ToolFailed, register
from recruitai.modules.identity import service as identity
from recruitai.modules.notes import service
from recruitai.modules.notes.schemas import MAX_BODY, NoteIn

FLAG = "notes_enabled"


async def _save_note(c: Call) -> dict[str, str]:
    try:
        data = NoteIn(
            title=" ".join(c.get("title").replace("\x00", "").split())[:200],
            body=c.get("body").replace("\x00", "").strip()[:MAX_BODY],
            source_url=c.get("source_url").strip() or None,
        )
    except ValidationError:
        raise ToolFailed(code="note_invalid") from None
    note = await service.create_note(c.db, org_id=c.org_id, data=data)
    return {"note_id": str(note.id)}


async def _summarise(c: Call) -> dict[str, str]:
    language: Language = (
        await identity.user_language(c.db, c.user_id) if c.user_id else "en"
    )
    await c.db.commit()  # nothing held open across the model call
    summary, quotes = await service.summarise(
        c.llm, text=c.get("text"), focus=c.get("focus"), language=language
    )
    return {
        "summary": summary,
        "quotes": "\n".join(f"- {' '.join(q.split())}" for q in quotes),
    }


register(
    Tool(
        "save_note",
        "web",
        (("title", True), ("body", True), ("source_url", False)),
        ("note_id",),
        effect="write",
        cap=Cap(100),  # a day; once: a resumed step does not save the note twice
        flag=FLAG,
        chat=True,
        mcp=True,
    ),
    _save_note,
)
register(
    Tool(
        "summarise",
        "web",
        (("text", True), ("focus", False)),
        ("summary", "quotes"),
        ai_uses=1,
        flag=FLAG,
        mcp=True,
    ),
    _summarise,
)
