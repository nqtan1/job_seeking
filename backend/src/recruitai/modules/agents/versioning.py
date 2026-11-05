"""Row helpers shared by the two versioned identities, helpers (agents) and flows: an atomic
"take the next version" and the plain update/archive of the identity row. Neutral on purpose, so
``helpers`` and ``flows`` can use it without depending on each other."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import rows_affected
from recruitai.core.errors import Conflict, ValidationFailed
from recruitai.modules.agents.flows.models import Flow
from recruitai.modules.agents.helpers.models import Agent
from recruitai.modules.agents.helpers.schemas import MAX_VERSIONS

Identity = type[Agent] | type[Flow]


async def update_row(
    session: AsyncSession,
    model: Identity,
    *,
    org_id: UUID,
    id: UUID,
    values: dict[str, Any],
) -> None:
    await session.execute(
        update(model).where(model.id == id, model.org_id == org_id).values(**values)
    )


async def archive_row(
    session: AsyncSession, model: Identity, *, org_id: UUID, id: UUID
) -> None:
    await update_row(
        session, model, org_id=org_id, id=id, values={"archived_at": func.now()}
    )


async def claim_next_version(
    session: AsyncSession,
    model: Identity,
    entity: Agent | Flow,
    *,
    org_id: UUID,
    based_on: int,
    noun: str,
) -> int:
    """Take version ``based_on + 1`` for this identity, or refuse. Atomic compare-and-set: only the
    editor that saw the latest version wins, and the row lock serializes two saves, so version
    numbers never collide. Returns the new version number."""
    if entity.archived_at is not None:
        raise Conflict(f"This {noun} is archived.")
    if based_on >= MAX_VERSIONS:
        raise ValidationFailed(
            f"A {noun} keeps at most {MAX_VERSIONS} versions: duplicate it to continue."
        )
    result = await session.execute(
        update(model)
        .where(
            model.id == entity.id,
            model.org_id == org_id,
            model.current_version == based_on,
            model.archived_at.is_(None),
        )
        .values(current_version=based_on + 1, updated_at=func.now())
    )
    if rows_affected(result) != 1:
        await session.rollback()
        raise Conflict(f"This {noun} changed elsewhere. Reload it and try again.")
    return based_on + 1
