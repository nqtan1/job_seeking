"""Steps and hand-offs of a run."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import rows_affected
from recruitai.modules.agents.flows.models import (
    FlowRunHandoff,
    FlowRunStep,
)

# steps and hand-offs


async def create_steps(
    session: AsyncSession, *, org_id: UUID, run_id: UUID, node_ids: list[UUID]
) -> None:
    session.add_all(
        FlowRunStep(org_id=org_id, run_id=run_id, node_id=n, position=i)
        for i, n in enumerate(node_ids)
    )
    await session.flush()


async def list_steps(
    session: AsyncSession, *, org_id: UUID, run_id: UUID
) -> list[FlowRunStep]:
    return list(
        (
            await session.execute(
                select(FlowRunStep)
                .where(FlowRunStep.org_id == org_id, FlowRunStep.run_id == run_id)
                .order_by(FlowRunStep.position)
            )
        ).scalars()
    )


async def claim_step(session: AsyncSession, *, org_id: UUID, step_id: UUID) -> bool:
    result = await session.execute(
        update(FlowRunStep)
        .where(
            FlowRunStep.id == step_id,
            FlowRunStep.org_id == org_id,
            FlowRunStep.status == "pending",
        )
        .values(status="running", started_at=func.now())
    )
    return rows_affected(result) == 1


async def set_step(
    session: AsyncSession,
    *,
    org_id: UUID,
    step_id: UUID,
    only_if: tuple[str, ...] | None = None,
    **values: Any,
) -> bool:
    """Update a step; with ``only_if`` only from those statuses, so a worker that lost its step
    (the run was resumed under it) cannot overwrite the new worker's result."""
    stmt = update(FlowRunStep).where(
        FlowRunStep.id == step_id, FlowRunStep.org_id == org_id
    )
    if only_if is not None:
        stmt = stmt.where(FlowRunStep.status.in_(only_if))
    return rows_affected(await session.execute(stmt.values(**values))) == 1


async def reset_unfinished_steps(
    session: AsyncSession, *, org_id: UUID, run_id: UUID
) -> None:
    """Failed or interrupted (running) steps go back to pending; done/skipped keep their output."""
    await session.execute(
        update(FlowRunStep)
        .where(
            FlowRunStep.org_id == org_id,
            FlowRunStep.run_id == run_id,
            FlowRunStep.status.in_(("failed", "running")),
        )
        .values(
            status="pending",
            error_code=None,
            started_at=None,
            finished_at=None,
            output=None,
            model=None,
            latency_ms=None,
        )
    )


async def record_handoff(
    session: AsyncSession, *, org_id: UUID, values: dict[str, Any]
) -> None:
    """Idempotent per (run, edge): a resumed step re-records the same hand-off."""
    stmt = (
        pg_insert(FlowRunHandoff)
        .values(org_id=org_id, **values)
        .on_conflict_do_update(
            index_elements=["run_id", "edge_id"],
            set_={"payload": values["payload"], "truncated": values["truncated"]},
        )
    )
    await session.execute(stmt)


async def list_handoffs(
    session: AsyncSession, *, org_id: UUID, run_id: UUID
) -> list[FlowRunHandoff]:
    return list(
        (
            await session.execute(
                select(FlowRunHandoff)
                .where(FlowRunHandoff.org_id == org_id, FlowRunHandoff.run_id == run_id)
                .order_by(FlowRunHandoff.created_at, FlowRunHandoff.id)
            )
        ).scalars()
    )
