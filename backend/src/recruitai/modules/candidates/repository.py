"""All SQL for the candidates module. Every query filters by org_id."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.ids import new_id
from recruitai.modules.candidates.models import CandidateProfile, UserMemory
from recruitai.modules.candidates.schemas import (
    MEMORY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    CVInformation,
)


async def get(
    session: AsyncSession, *, org_id: UUID, for_update: bool = False
) -> CandidateProfile | None:
    """``for_update`` locks the row until commit: a read-modify-write (PATCH) must not
    interleave with another one, or the second writer silently drops the first's section."""
    stmt = select(CandidateProfile).where(CandidateProfile.org_id == org_id)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert(
    session: AsyncSession,
    *,
    org_id: UUID,
    document_id: UUID | None,
    info: CVInformation,
) -> CandidateProfile:
    """Atomic on ``UNIQUE(org_id)``: two concurrent extractions can't create two profiles."""
    values = {
        "document_id": document_id,
        "name": info.personal_info.name,
        "email": info.personal_info.email,
        "data": info.model_dump(mode="json"),
        "schema_version": SCHEMA_VERSION,
    }
    stmt = (
        insert(CandidateProfile)
        .values(id=new_id(), org_id=org_id, **values)
        .on_conflict_do_update(
            index_elements=[CandidateProfile.org_id],
            set_={**values, "updated_at": func.now()},
        )
        .returning(CandidateProfile)
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()


async def get_memory(session: AsyncSession, *, org_id: UUID) -> UserMemory | None:
    stmt = select(UserMemory).where(UserMemory.org_id == org_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def lock_memory(session: AsyncSession, *, org_id: UUID) -> UserMemory:
    """The org's memory row, created if missing and locked until commit: two concurrent writes
    (a chat ``remember`` and a Settings save) must not drop each other's facts."""
    await session.execute(
        insert(UserMemory).values(org_id=org_id).on_conflict_do_nothing()
    )
    stmt = (
        select(UserMemory)
        .where(UserMemory.org_id == org_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()


async def set_memory(
    session: AsyncSession, row: UserMemory, facts: list[dict[str, Any]]
) -> None:
    row.facts = facts
    row.schema_version = MEMORY_SCHEMA_VERSION
    await session.flush()
