"""All SQL for the candidates module. Every query filters by org_id."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.ids import new_id
from recruitai.modules.candidates.models import CandidateProfile
from recruitai.modules.candidates.schemas import SCHEMA_VERSION, CVInformation


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
