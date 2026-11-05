"""All SQL for flows and runs. Every query filters by org_id."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import rows_affected
from recruitai.modules.agents.models import (
    Flow,
    FlowEffect,
    FlowRun,
    FlowRunHandoff,
    FlowRunStep,
    FlowSchedule,
    FlowVersion,
)

ACTIVE = ("queued", "running")
LIVE = (*ACTIVE, "waiting")  # a waiting run will still change: not ended, not deletable
MAX_WAITING_RUNS_PER_ORG = 10


async def count_flows(
    session: AsyncSession, *, org_id: UUID, include_archived: bool = False
) -> int:
    stmt = select(func.count()).select_from(Flow).where(Flow.org_id == org_id)
    if not include_archived:
        stmt = stmt.where(Flow.archived_at.is_(None))
    return (await session.execute(stmt)).scalar_one()


async def create_flow(
    session: AsyncSession, *, org_id: UUID, values: dict[str, Any]
) -> Flow:
    flow = Flow(org_id=org_id, **values)
    session.add(flow)
    await session.flush()
    await session.refresh(flow)
    return flow


async def get_flow(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> Flow | None:
    return (
        await session.execute(
            select(Flow).where(Flow.id == flow_id, Flow.org_id == org_id)
        )
    ).scalar_one_or_none()


async def list_flows(session: AsyncSession, *, org_id: UUID) -> list[Flow]:
    return list(
        (
            await session.execute(
                select(Flow)
                .where(Flow.org_id == org_id, Flow.archived_at.is_(None))
                .order_by(Flow.updated_at.desc(), Flow.id)
            )
        ).scalars()
    )


async def add_flow_version(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID, values: dict[str, Any]
) -> FlowVersion:
    row = FlowVersion(org_id=org_id, flow_id=flow_id, **values)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_flow_version(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID, version: int
) -> FlowVersion | None:
    return (
        await session.execute(
            select(FlowVersion).where(
                FlowVersion.org_id == org_id,
                FlowVersion.flow_id == flow_id,
                FlowVersion.version == version,
            )
        )
    ).scalar_one_or_none()


async def get_flow_version_by_id(
    session: AsyncSession, *, org_id: UUID, version_id: UUID
) -> FlowVersion | None:
    return (
        await session.execute(
            select(FlowVersion).where(
                FlowVersion.org_id == org_id, FlowVersion.id == version_id
            )
        )
    ).scalar_one_or_none()


async def list_flow_versions(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> list[FlowVersion]:
    return list(
        (
            await session.execute(
                select(FlowVersion)
                .where(FlowVersion.org_id == org_id, FlowVersion.flow_id == flow_id)
                .order_by(FlowVersion.version.desc())
            )
        ).scalars()
    )


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
    **values: Any,
) -> bool:
    """Update a run; with ``only_if`` the change applies only from those statuses (so a cancel can
    never overwrite a run that just finished). Returns whether a row changed."""
    stmt = update(FlowRun).where(FlowRun.id == run_id, FlowRun.org_id == org_id)
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
    rows = await session.execute(
        select(FlowRun.org_id, FlowRun.id).where(
            FlowRun.status == "running", FlowRun.updated_at < cutoff
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


async def claim_effect(
    session: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    run_id: UUID,
    node_id: UUID,
    kind: str,
    daily_cap: int,
    global_cap: int | None = None,
    once: bool = True,
) -> str:
    """``"new"`` (go ahead, the row is written), ``"done"`` (this step already did it) or
    ``"capped"`` (a cap was reached). A per-user advisory lock makes count + insert atomic; a cap
    over everyone also takes a short lock of its own, so parallel runs cannot overshoot it.
    ``once=False`` (a repeatable action such as reading a page) only counts: a step that already
    has its row simply runs again."""
    await session.execute(
        select(
            func.pg_advisory_xact_lock(func.hashtextextended(f"effects:{user_id}", 0))
        )
    )
    if (
        await session.execute(
            select(FlowEffect.id).where(
                FlowEffect.run_id == run_id, FlowEffect.node_id == node_id
            )
        )
    ).first():
        return "done" if once else "new"
    today = func.date_trunc("day", func.now())
    used = (
        await session.execute(
            select(func.count(FlowEffect.id)).where(
                FlowEffect.user_id == user_id,
                FlowEffect.kind == kind,
                FlowEffect.created_at >= today,
            )
        )
    ).scalar_one()
    if used >= daily_cap:
        return "capped"
    if (
        global_cap is not None
    ):  # everyone together: a flood of accounts cannot get past this
        await session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"effects:all:{kind}", 0)
                )
            )
        )
        everyone = (
            await session.execute(
                select(func.count(FlowEffect.id)).where(
                    FlowEffect.kind == kind, FlowEffect.created_at >= today
                )
            )
        ).scalar_one()
        if everyone >= global_cap:
            return "capped"
    session.add(
        FlowEffect(
            org_id=org_id, user_id=user_id, run_id=run_id, node_id=node_id, kind=kind
        )
    )
    await session.flush()
    return "new"


async def release_effect(session: AsyncSession, *, run_id: UUID, node_id: UUID) -> None:
    """Give an effect's slot back (the outside call was refused, nothing happened)."""
    await session.execute(
        delete(FlowEffect).where(
            FlowEffect.run_id == run_id, FlowEffect.node_id == node_id
        )
    )


async def has_waiting_run(session: AsyncSession, *, schedule_id: UUID) -> bool:
    return (
        await session.execute(
            select(FlowRun.id)
            .where(FlowRun.schedule_id == schedule_id, FlowRun.status == "waiting")
            .limit(1)
        )
    ).first() is not None
