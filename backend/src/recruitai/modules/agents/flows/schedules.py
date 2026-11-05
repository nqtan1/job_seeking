"""Scheduled runs (ADR 0031): "run this flow every day at 8:00" for people who do not want to press
Run. The schedule belongs to the user, runs their own flow with the inputs they saved, and spends
their daily AI quota like any run. It pauses itself after repeated failures and when the account
goes dormant, so nobody pays for automation they forgot."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import AppError, NotFound, ValidationFailed
from recruitai.modules.agents.flows import repository as repo
from recruitai.modules.agents.flows import runs as flow_runs
from recruitai.modules.agents.flows import service as flows
from recruitai.modules.agents.flows.models import FlowSchedule
from recruitai.modules.agents.flows.schemas import RunIn, ScheduleIn
from recruitai.modules.identity import service as identity

logger = logging.getLogger(__name__)

MAX_SCHEDULES_PER_ORG = 5
FAILURES_BEFORE_PAUSE = 3
DORMANT_AFTER = timedelta(days=30)  # no sign-in for this long: automated work stops
BATCH = 20  # schedules handled per sweep; the rest wait for the next one (5 minutes)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationFailed("Unknown time zone.") from None


def next_run(
    cadence: str, at_time: str | None, weekday: int | None, tz: str, after: datetime
) -> datetime:
    """The first slot strictly after ``after`` (UTC, aware). Local times follow the zone's rules,
    daylight saving included."""
    if cadence == "hourly":
        return after.astimezone(UTC).replace(
            minute=0, second=0, microsecond=0
        ) + timedelta(hours=1)
    zone = _zone(tz)
    hh, mm = (int(p) for p in (at_time or "00:00").split(":"))
    local = after.astimezone(zone)
    day = local.date()
    for _ in range(8):  # at most a week plus today
        slot = datetime.combine(day, time(hh, mm), tzinfo=zone)
        if slot.astimezone(UTC) > after and (
            cadence == "daily" or day.weekday() == weekday
        ):
            return slot.astimezone(
                UTC
            )  # compared in UTC: a repeated local hour must not go backwards
        day += timedelta(days=1)
    raise ValidationFailed("That schedule never runs.")  # unreachable for valid input


async def create_schedule(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, flow_id: UUID, data: ScheduleIn
) -> FlowSchedule:
    _zone(data.timezone)  # an unknown zone is refused even for an hourly schedule
    # the same checks as pressing Run now: a schedule that could never run is refused up front
    await flow_runs.prepare_run(
        db,
        org_id=org_id,
        flow_id=flow_id,
        data=RunIn(inputs=data.inputs, job_id=data.job_id),
    )
    await repo.lock_org_runs(db, org_id=org_id)  # two requests cannot both pass the cap
    if await repo.count_schedules(db, org_id=org_id) >= MAX_SCHEDULES_PER_ORG:
        raise ValidationFailed(
            f"You can have at most {MAX_SCHEDULES_PER_ORG} schedules."
        )
    schedule = await repo.create_schedule(
        db,
        org_id=org_id,
        values={
            "user_id": user_id,
            "flow_id": flow_id,
            "cadence": data.cadence,
            "at_time": data.at_time,
            "weekday": data.weekday,
            "timezone": data.timezone,
            "inputs": dict(data.inputs),
            "job_id": data.job_id,
            "next_run_at": next_run(
                data.cadence,
                data.at_time,
                data.weekday,
                data.timezone,
                datetime.now(UTC),
            ),
        },
    )
    await db.commit()
    return schedule


async def list_schedules(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> list[FlowSchedule]:
    await flows.get_flow(db, org_id=org_id, flow_id=flow_id)
    return await repo.list_schedules(db, org_id=org_id, flow_id=flow_id)


async def _get(db: AsyncSession, *, org_id: UUID, schedule_id: UUID) -> FlowSchedule:
    schedule = await repo.get_schedule(db, org_id=org_id, schedule_id=schedule_id)
    if schedule is None:
        raise NotFound("Schedule not found.")
    return schedule


async def set_enabled(
    db: AsyncSession, *, org_id: UUID, schedule_id: UUID, enabled: bool
) -> FlowSchedule:
    """Turning a schedule back on clears its pause and starts counting from now (no catch-up)."""
    s = await _get(db, org_id=org_id, schedule_id=schedule_id)
    if enabled and s.enabled and s.paused_reason is None:
        return s  # already running: a repeated request must not push the next slot back
    values: dict[str, object] = {"enabled": enabled}
    if enabled:
        # turning it back on needs a flow that can run today (deleted job, archived or edited flow)
        await flow_runs.prepare_run(
            db,
            org_id=org_id,
            flow_id=s.flow_id,
            data=RunIn(inputs=dict(s.inputs), job_id=s.job_id),
        )
        values |= {
            "paused_reason": None,
            "consecutive_failures": 0,
            "next_run_at": next_run(
                s.cadence, s.at_time, s.weekday, s.timezone, datetime.now(UTC)
            ),
        }
    await repo.update_schedule(
        db, org_id=org_id, schedule_id=schedule_id, values=values
    )
    await db.commit()
    await db.refresh(s)
    return s


async def delete_schedule(db: AsyncSession, *, org_id: UUID, schedule_id: UUID) -> None:
    if not await repo.delete_schedule(db, org_id=org_id, schedule_id=schedule_id):
        raise NotFound("Schedule not found.")
    await db.commit()


@dataclass(frozen=True)
class _Claim:
    """Plain values of a claimed schedule: a rollback expires ORM rows, these survive it."""

    id: UUID
    org_id: UUID
    user_id: UUID
    flow_id: UUID
    inputs: dict[str, str]
    job_id: UUID | None
    slot: datetime
    failures: int


async def _count_failure(db: AsyncSession, c: _Claim) -> None:
    try:
        await _save_failure(db, c)
    except Exception as exc:  # noqa: BLE001  (a database hiccup must not lose the other slots)
        await db.rollback()
        logger.error("failure not counted", extra={"error_type": type(exc).__name__})


async def _save_failure(db: AsyncSession, c: _Claim) -> None:
    failures = c.failures + 1
    values: dict[str, object] = {"consecutive_failures": failures}
    if failures >= FAILURES_BEFORE_PAUSE:
        values["paused_reason"] = "failures"
    await repo.update_schedule(db, org_id=c.org_id, schedule_id=c.id, values=values)
    await db.commit()


async def run_due(db: AsyncSession, *, now: datetime) -> int:
    """Start every schedule whose slot has come. A slot is claimed (next slot saved) BEFORE the run
    is queued and the run carries an idempotency key made from the slot, so a duplicate sweep or a
    crash can never start the same slot twice; a missed slot is skipped, never replayed in a burst."""
    due = await repo.claim_due_schedules(db, now=now, limit=BATCH)
    owners = await identity.active_owner_ids(
        db, org_ids=list({s.org_id for s in due}), active_since=now - DORMANT_AFTER
    )
    started = 0
    claimed: list[_Claim] = []
    for s in due:
        if s.org_id not in owners:  # dormant or blocked: stop spending on their behalf
            await repo.update_schedule(
                db,
                org_id=s.org_id,
                schedule_id=s.id,
                values={"paused_reason": "inactive"},
            )
            continue
        if await repo.has_waiting_run(db, schedule_id=s.id):
            # its last run is still sleeping on a wait: never pile runs up behind it. The slot is
            # skipped (next one saved), else parked rows stay the oldest and fill every batch.
            await repo.update_schedule(
                db,
                org_id=s.org_id,
                schedule_id=s.id,
                values={
                    "next_run_at": next_run(
                        s.cadence,
                        s.at_time,
                        s.weekday,
                        s.timezone,
                        max(now, s.next_run_at),
                    )
                },
            )
            continue
        last, made_at = await repo.last_scheduled_run(db, schedule_id=s.id)
        # A failed run counts once (only if it was queued after the previous claim, so a refused
        # start can never make the same failure count again), a finished one resets; anything else
        # (nothing yet, still running, cancelled) keeps the count.
        fresh = made_at is not None and (
            s.last_run_at is None or made_at > s.last_run_at
        )
        failures = s.consecutive_failures
        if last == "done":
            failures = 0
        elif last == "failed" and fresh:
            failures += 1
        if failures >= FAILURES_BEFORE_PAUSE:
            await repo.update_schedule(
                db,
                org_id=s.org_id,
                schedule_id=s.id,
                values={"paused_reason": "failures", "consecutive_failures": failures},
            )
            continue
        slot = s.next_run_at
        values: dict[str, object] = {
            "next_run_at": next_run(
                s.cadence, s.at_time, s.weekday, s.timezone, max(now, slot)
            ),
            "consecutive_failures": failures,
        }
        if last == "failed" and fresh:
            values["last_run_at"] = (
                now  # that failure is counted now: never count it twice
            )
        await repo.update_schedule(db, org_id=s.org_id, schedule_id=s.id, values=values)
        claimed.append(
            _Claim(
                s.id,
                s.org_id,
                s.user_id,
                s.flow_id,
                dict(s.inputs),
                s.job_id,
                slot,
                failures,
            )
        )
    await db.commit()  # the slots are ours; release the row locks before the slow part

    for c in claimed:
        try:
            _, created = await flow_runs.start_run(
                db,
                org_id=c.org_id,
                user_id=c.user_id,
                flow_id=c.flow_id,
                data=RunIn(inputs=c.inputs, job_id=c.job_id),
                idempotency_key=f"sched:{c.id}:{int(c.slot.timestamp())}",
                schedule_id=c.id,
            )
            if created:  # last_run_at marks runs actually made, so a later failure is still fresh
                started += 1
                await repo.update_schedule(
                    db, org_id=c.org_id, schedule_id=c.id, values={"last_run_at": now}
                )
                await db.commit()
        except (
            flow_runs.OrgBusy
        ) as exc:  # busy right now: skip this slot, it is not a failure
            await db.rollback()
            logger.info(
                "scheduled run skipped",
                extra={"schedule_id": str(c.id), "code": exc.code},
            )
        except AppError as exc:
            await db.rollback()
            logger.info(
                "scheduled run refused",
                extra={"schedule_id": str(c.id), "code": exc.code},
            )
            await _count_failure(db, c)
        except Exception as exc:  # noqa: BLE001  (one bad schedule must not stop the others)
            await db.rollback()
            logger.error(
                "scheduled run failed", extra={"error_type": type(exc).__name__}
            )
            await _count_failure(db, c)
    return started
