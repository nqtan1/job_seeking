"""Runs: lifecycle, counts, claims and sweeps (base of the repository package)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import rows_affected
from recruitai.modules.agents.flows.models import (
    Flow,
    FlowRun,
    FlowRunHandoff,
    FlowRunStep,
    FlowVersion,
)

ACTIVE = ("queued", "running")
LIVE = (*ACTIVE, "waiting")  # a waiting run will still change: not ended, not deletable
MAX_WAITING_RUNS_PER_ORG = 10


# runs


async def create_run(
    session: AsyncSession, *, org_id: UUID, values: dict[str, Any]
) -> FlowRun:
    run = FlowRun(org_id=org_id, **values)
    session.add(run)
    await session.flush()
    await session.refresh(run)
    return run


async def get_run(
    session: AsyncSession, *, org_id: UUID, run_id: UUID
) -> FlowRun | None:
    return (
        await session.execute(
            select(FlowRun).where(FlowRun.id == run_id, FlowRun.org_id == org_id)
        )
    ).scalar_one_or_none()


async def find_run_by_key(
    session: AsyncSession, *, org_id: UUID, key: str
) -> FlowRun | None:
    return (
        await session.execute(
            select(FlowRun).where(
                FlowRun.org_id == org_id, FlowRun.idempotency_key == key
            )
        )
    ).scalar_one_or_none()


async def count_active_runs(session: AsyncSession, *, org_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(FlowRun)
            .where(
                FlowRun.org_id == org_id,
                FlowRun.status.in_(ACTIVE),
                FlowRun.parent_run_id.is_(
                    None
                ),  # runs started by a for_each have their own cap
            )
        )
    ).scalar_one()


async def count_active_children(session: AsyncSession, *, org_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(FlowRun)
            .where(
                FlowRun.org_id == org_id,
                FlowRun.status.in_(ACTIVE),
                FlowRun.trigger == "flow",
            )
        )
    ).scalar_one()


async def count_waiting_runs(session: AsyncSession, *, org_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(FlowRun)
            .where(FlowRun.org_id == org_id, FlowRun.status == "waiting")
        )
    ).scalar_one()


async def list_runs(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID, limit: int
) -> list[FlowRun]:
    return list(
        (
            await session.execute(
                select(FlowRun)
                .where(FlowRun.org_id == org_id, FlowRun.flow_id == flow_id)
                .order_by(FlowRun.created_at.desc(), FlowRun.id.desc())
                .limit(limit)
            )
        ).scalars()
    )


async def claim_run(session: AsyncSession, *, org_id: UUID, run_id: UUID) -> bool:
    """queued (or waiting and due) -> running, once: a duplicate or early delivery of the task finds
    nothing to claim."""
    result = await session.execute(
        update(FlowRun)
        .where(
            FlowRun.id == run_id,
            FlowRun.org_id == org_id,
            or_(
                FlowRun.status == "queued",
                and_(FlowRun.status == "waiting", FlowRun.wake_at <= func.now()),
            ),
        )
        .values(
            status="running",
            wake_at=None,
            started_at=func.coalesce(FlowRun.started_at, func.now()),
        )
    )
    return rows_affected(result) == 1


async def set_run(
    session: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
    only_if: tuple[str, ...] | None = None,
    seen_updated_at: datetime | None = None,
    **values: Any,
) -> bool:
    """Update a run; with ``only_if`` the change applies only from those statuses (so a cancel can
    never overwrite a run that just finished), with ``seen_updated_at`` only if nobody touched the
    run since it was read. Returns whether a row changed."""
    stmt = update(FlowRun).where(FlowRun.id == run_id, FlowRun.org_id == org_id)
    if seen_updated_at is not None:
        stmt = stmt.where(FlowRun.updated_at == seen_updated_at)
    if only_if is not None:
        stmt = stmt.where(FlowRun.status.in_(only_if))
    result = await session.execute(stmt.values(**values))
    return rows_affected(result) == 1


async def touch_run(session: AsyncSession, *, org_id: UUID, run_id: UUID) -> None:
    """Heartbeat: a run that keeps moving is never taken for stuck."""
    await session.execute(
        update(FlowRun)
        .where(
            FlowRun.id == run_id, FlowRun.org_id == org_id, FlowRun.status == "running"
        )
        .values(updated_at=func.now())
    )


async def lock_org_runs(session: AsyncSession, *, org_id: UUID) -> None:
    """Serialize "count the live runs, then start one" per org (released at commit/rollback)."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(f"runs:{org_id}", 0)))
    )


async def fail_running_steps(
    session: AsyncSession, *, org_id: UUID, run_id: UUID, code: str
) -> None:
    """Mark the in-flight step failed, so the UI never shows a spinner on a run that ended."""
    await session.execute(
        update(FlowRunStep)
        .where(
            FlowRunStep.org_id == org_id,
            FlowRunStep.run_id == run_id,
            FlowRunStep.status.in_(("running", "waiting")),
        )
        .values(status="failed", error_code=code, finished_at=func.now())
    )


async def fail_active_run(
    session: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
    code: str,
    older_than: datetime | None = None,
) -> bool:
    """End a queued or running run as failed (and its in-flight step). A finished or cancelled run
    is left alone; with ``older_than`` a run that moved since is left alone too (the sweep)."""
    stmt = update(FlowRun).where(
        FlowRun.id == run_id, FlowRun.org_id == org_id, FlowRun.status.in_(ACTIVE)
    )
    if older_than is not None:
        stmt = stmt.where(FlowRun.updated_at < older_than)
    result = await session.execute(
        stmt.values(status="failed", error_code=code, finished_at=func.now())
    )
    if rows_affected(result) != 1:
        return False
    await fail_running_steps(session, org_id=org_id, run_id=run_id, code=code)
    return True


async def stale_running(
    session: AsyncSession, *, cutoff: datetime
) -> list[tuple[UUID, UUID]]:
    """Active runs silent since ``cutoff``: running ones whose worker died, and queued ones whose
    job was lost (queue wait is seconds; the cutoff is minutes)."""
    rows = await session.execute(
        select(FlowRun.org_id, FlowRun.id).where(
            FlowRun.status.in_(ACTIVE), FlowRun.updated_at < cutoff
        )
    )
    return [(o, r) for o, r in rows.all()]


async def fail_lost_waiting(
    session: AsyncSession, *, org_id: UUID, run_id: UUID, cutoff: datetime
) -> bool:
    """A waiting run whose wake-up job never came (lost): failed, so the user can resume it."""
    result = await session.execute(
        update(FlowRun)
        .where(
            FlowRun.id == run_id,
            FlowRun.org_id == org_id,
            FlowRun.status == "waiting",
            FlowRun.wake_at < cutoff,
        )
        .values(
            status="failed",
            error_code="wake_lost",
            wake_at=None,
            finished_at=func.now(),
        )
    )
    if rows_affected(result) != 1:
        return False
    await fail_running_steps(session, org_id=org_id, run_id=run_id, code="wake_lost")
    return True


async def lost_waiting(
    session: AsyncSession, *, cutoff: datetime
) -> list[tuple[UUID, UUID]]:
    rows = await session.execute(
        select(FlowRun.org_id, FlowRun.id).where(
            FlowRun.status == "waiting", FlowRun.wake_at < cutoff
        )
    )
    return [(o, r) for o, r in rows.all()]


async def current_versions(
    session: AsyncSession, *, org_id: UUID
) -> dict[UUID, FlowVersion]:
    """The current version of every flow of the org, in one query."""
    rows = await session.execute(
        select(FlowVersion)
        .join(
            Flow,
            (Flow.id == FlowVersion.flow_id)
            & (Flow.current_version == FlowVersion.version),
        )
        .where(FlowVersion.org_id == org_id, Flow.org_id == org_id)
    )
    return {v.flow_id: v for v in rows.scalars()}


async def finish_run(
    session: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
    status: str,
    error_code: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    """Only from running: a cancel that landed meanwhile is never overwritten."""
    await session.execute(
        update(FlowRun)
        .where(
            FlowRun.id == run_id, FlowRun.org_id == org_id, FlowRun.status == "running"
        )
        .values(
            status=status,
            error_code=error_code,
            result=result,
            finished_at=func.now(),
        )
    )


async def all_for_org(
    session: AsyncSession, *, org_id: UUID
) -> tuple[
    list[Flow],
    list[FlowVersion],
    list[FlowRun],
    list[FlowRunStep],
    list[FlowRunHandoff],
]:
    async def rows(model: Any) -> list[Any]:
        return list(
            (
                await session.execute(select(model).where(model.org_id == org_id))
            ).scalars()
        )

    return (
        await rows(Flow),
        await rows(FlowVersion),
        await rows(FlowRun),
        await rows(FlowRunStep),
        await rows(FlowRunHandoff),
    )


async def delete_runs_older_than(session: AsyncSession, *, cutoff: datetime) -> int:
    """Ended runs only (steps and hand-offs go with them by cascade)."""
    result = await session.execute(
        delete(FlowRun).where(FlowRun.status.not_in(LIVE), FlowRun.created_at < cutoff)
    )
    return rows_affected(result)


# the "all runs" page


async def list_org_runs(
    session: AsyncSession,
    *,
    org_id: UUID,
    status: str | None,
    flow_id: UUID | None,
    before_id: UUID | None,
    limit: int,
) -> list[tuple[FlowRun, str]]:
    """Newest first, with the flow's name. Ids are UUIDv7 (time-ordered, unique), so ``before_id`` =
    the last id seen pages exactly, even when two runs share a timestamp."""
    stmt = (
        select(FlowRun, Flow.name)
        .join(Flow, Flow.id == FlowRun.flow_id)
        .where(FlowRun.org_id == org_id, Flow.org_id == org_id)
    )
    if status:
        stmt = stmt.where(FlowRun.status == status)
    if flow_id:
        stmt = stmt.where(FlowRun.flow_id == flow_id)
    if before_id:
        stmt = stmt.where(FlowRun.id < before_id)
    rows = await session.execute(stmt.order_by(FlowRun.id.desc()).limit(limit))
    return [(r, name) for r, name in rows.all()]


async def has_waiting_run(session: AsyncSession, *, schedule_id: UUID) -> bool:
    return (
        await session.execute(
            select(FlowRun.id)
            .where(FlowRun.schedule_id == schedule_id, FlowRun.status == "waiting")
            .limit(1)
        )
    ).first() is not None


async def run_status(
    session: AsyncSession, *, org_id: UUID, run_id: UUID
) -> str | None:
    return (
        await session.execute(
            select(FlowRun.status).where(FlowRun.id == run_id, FlowRun.org_id == org_id)
        )
    ).scalar_one_or_none()
