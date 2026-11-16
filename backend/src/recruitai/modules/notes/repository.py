"""All SQL for the notes module. Every query filters by org_id."""

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.notes.models import Note
from recruitai.modules.notes.schemas import NoteIn


async def add(session: AsyncSession, *, org_id: UUID, data: NoteIn) -> Note:
    row = Note(org_id=org_id, **data.model_dump())
    session.add(row)
    await session.flush()
    await session.refresh(row)  # server-side created_at
    return row


async def get(session: AsyncSession, *, org_id: UUID, note_id: UUID) -> Note | None:
    return (
        await session.execute(
            select(Note).where(Note.org_id == org_id, Note.id == note_id)
        )
    ).scalar_one_or_none()


async def list_for_org(
    session: AsyncSession, *, org_id: UUID, limit: int, offset: int
) -> list[Note]:
    rows = await session.execute(
        select(Note)
        .where(Note.org_id == org_id)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


async def delete(session: AsyncSession, *, org_id: UUID, note_id: UUID) -> bool:
    stmt = sa_delete(Note).where(Note.org_id == org_id, Note.id == note_id)
    return (await session.execute(stmt.returning(Note.id))).first() is not None


async def count_for_org(session: AsyncSession, *, org_id: UUID) -> int:
    """After a per-org lock (released at commit): two saves cannot both take the last slot."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(f"notes:{org_id}", 0)))
    )
    return (
        await session.execute(
            select(func.count()).select_from(Note).where(Note.org_id == org_id)
        )
    ).scalar_one()


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[Note]:
    rows = await session.execute(
        select(Note).where(Note.org_id == org_id).order_by(Note.created_at)
    )
    return list(rows.scalars())
