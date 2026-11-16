"""Notes service. No FastAPI imports. Other modules are reached only through their services,"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway, TextPart, without_nul
from recruitai.ai.prompts.language import with_language
from recruitai.ai.prompts.summarise import MESSAGE, PROMPT_VERSION, SYSTEM_PROMPT
from recruitai.ai.text import fence, locate
from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.language import Language
from recruitai.modules.notes import repository
from recruitai.modules.notes.models import Note
from recruitai.modules.notes.schemas import MAX_BODY, NoteIn, Summary

MAX_NOTES_PER_ORG = 500
MAX_QUOTES = 5


async def create_note(db: AsyncSession, *, org_id: UUID, data: NoteIn) -> Note:
    if await repository.count_for_org(db, org_id=org_id) >= MAX_NOTES_PER_ORG:
        raise ValidationFailed(
            f"You can keep at most {MAX_NOTES_PER_ORG} notes: delete one first.",
            code="notes_limit",
        )
    row = await repository.add(db, org_id=org_id, data=data)
    await db.commit()
    return row


async def get_note(db: AsyncSession, *, org_id: UUID, note_id: UUID) -> Note:
    row = await repository.get(db, org_id=org_id, note_id=note_id)
    if row is None:
        raise NotFound("Note not found.")
    return row


async def list_notes(
    db: AsyncSession, *, org_id: UUID, limit: int, offset: int
) -> list[Note]:
    return await repository.list_for_org(db, org_id=org_id, limit=limit, offset=offset)


async def delete_note(db: AsyncSession, *, org_id: UUID, note_id: UUID) -> None:
    if not await repository.delete(db, org_id=org_id, note_id=note_id):
        raise NotFound("Note not found.")
    await db.commit()


def _grounded(quotes: list[str], text: str) -> list[str]:
    """Each quote as the exact passage of ``text`` it copies, or dropped."""
    found = (locate(q, text) for q in quotes)
    return list(dict.fromkeys(f for f in found if f))[:MAX_QUOTES]


async def summarise(
    llm: LLMGateway, *, text: str, focus: str, language: Language
) -> tuple[str, list[str]]:
    """One fast call; only the quotes found in ``text`` are kept."""
    # ponytail: a long page is cut at MAX_BODY; chunk it if users need more
    text = text[:MAX_BODY]
    out = without_nul(
        await llm.generate(
            schema=Summary,
            system=with_language(SYSTEM_PROMPT, language),
            parts=[
                TextPart(MESSAGE.format(focus=fence(focus[:500]), text=fence(text)))
            ],
            feature=PROMPT_VERSION,
        )
    )
    return out.summary[:4000], _grounded(out.quotes[: 2 * MAX_QUOTES], text)


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, Any]]]:
    return {"notes": rows_as_dicts(await repository.all_for_org(db, org_id=org_id))}
