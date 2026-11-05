"""Schedule rows and the due-schedule claim."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import rows_affected
from recruitai.modules.agents.flows.models import (
    FlowRun,
    FlowSchedule,
)

# schedules


async def count_schedules(session: AsyncSession, *, org_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(FlowSchedule)
            .where(FlowSchedule.org_id == org_id)
        )
    ).scalar_one()


async def create_schedule(
    session: AsyncSession, *, org_id: UUID, values: dict[str, Any]
) -> FlowSchedule:
    row = FlowSchedule(org_id=org_id, **values)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_schedule(
    session: AsyncSession, *, org_id: UUID, schedule_id: UUID
) -> FlowSchedule | None:
    return (
        await session.execute(
            select(FlowSchedule).where(
                FlowSchedule.id == schedule_id, FlowSchedule.org_id == org_id
            )
        )
    ).scalar_one_or_none()


async def list_schedules(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> list[FlowSchedule]:
    return list(
        (
            await session.execute(
                select(FlowSchedule)
                .where(FlowSchedule.org_id == org_id, FlowSchedule.flow_id == flow_id)
                .order_by(FlowSchedule.created_at, FlowSchedule.id)
            )
        ).scalars()
    )


async def update_schedule(
    session: AsyncSession, *, org_id: UUID, schedule_id: UUID, values: dict[str, Any]
) -> None:
    await session.execute(
        update(FlowSchedule)
        .where(FlowSchedule.id == schedule_id, FlowSchedule.org_id == org_id)
        .values(**values)
    )


async def delete_schedule(
    session: AsyncSession, *, org_id: UUID, schedule_id: UUID
) -> bool:
    result = await session.execute(
        delete(FlowSchedule).where(
            FlowSchedule.id == schedule_id, FlowSchedule.org_id == org_id
        )
    )
    return rows_affected(result) == 1


async def claim_due_schedules(
    session: AsyncSession, *, now: datetime, limit: int
) -> list[FlowSchedule]:
    """Live schedules whose slot has come. ``SKIP LOCKED``: two sweeps never take the same row."""
    rows = await session.execute(
        select(FlowSchedule)
        .where(
            FlowSchedule.enabled.is_(True),
            FlowSchedule.paused_reason.is_(None),
            FlowSchedule.next_run_at <= now,
        )
        .order_by(FlowSchedule.next_run_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(rows.scalars())


async def last_scheduled_run(
    session: AsyncSession, *, schedule_id: UUID
) -> tuple[str | None, datetime | None]:
    row = (
        await session.execute(
            select(FlowRun.status, FlowRun.created_at)
            .where(FlowRun.schedule_id == schedule_id)
            .order_by(FlowRun.created_at.desc())
            .limit(1)
        )
    ).first()
    return (row[0], row[1]) if row else (None, None)


async def schedules_for_org(
    session: AsyncSession, *, org_id: UUID
) -> list[FlowSchedule]:
    return list(
        (
            await session.execute(
                select(FlowSchedule).where(FlowSchedule.org_id == org_id)
            )
        ).scalars()
    )
