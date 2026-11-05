"""Flow recovery edges: stranded queued runs, schedule sweeps (starvation, failure counting,
isolation), fan_out after a cancel, and two workers resuming one run."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from recruitai.core.errors import Conflict
from recruitai.modules.agents.flows import repository as repo
from recruitai.modules.agents.flows import runs as flow_runs
from recruitai.modules.agents.flows import schedules
from recruitai.modules.agents.flows import service as flows
from recruitai.modules.agents.flows.models import FlowRun
from tests.integration.test_flows import (
    BASE,
    edge,
    input_node,
    make_flow,
    org_of,
    output_node,
)


async def simple_flow(client, who) -> dict:
    i, o = input_node("n"), output_node("r")
    return await make_flow(client, who, [i, o], [edge(i, o, {"r": "{{n}}"})])


async def queue_run(client, who, flow) -> UUID:
    r = await client.post(
        f"{BASE}/flows/{flow['id']}/runs", headers=who, json={"inputs": {"n": "x"}}
    )
    assert r.status_code == 202, r.text
    return UUID(r.json()["id"])


async def status_of(db, org, run_id) -> str:
    db.expire_all()
    return (await repo.get_run(db, org_id=org, run_id=run_id)).status


async def active_user(client, db, who) -> None:
    uid = (await client.get(f"{BASE}/me", headers=who)).json()["user"]["id"]
    await db.execute(
        text("UPDATE users SET last_active_at = now() WHERE id = :u"), {"u": uid}
    )


async def new_schedule(client, who, flow) -> UUID:
    body = {"cadence": "hourly", "timezone": "UTC", "inputs": {"n": "hi"}}
    r = await client.post(
        f"{BASE}/flows/{flow['id']}/schedules", headers=who, json=body
    )
    return UUID(r.json()["id"])


async def make_due(db, org, sid, minutes_ago=5, **extra) -> None:
    await repo.update_schedule(
        db,
        org_id=org,
        schedule_id=sid,
        values={
            "next_run_at": datetime.now(UTC) - timedelta(minutes=minutes_ago),
            **extra,
        },
    )
    await db.commit()


async def test_a_queued_run_whose_job_was_lost_is_failed_but_a_fresh_one_is_not(
    client, db_session, task_app, ada
):
    org = await org_of(client, ada)
    flow = await simple_flow(client, ada)
    old, fresh = await queue_run(client, ada, flow), await queue_run(client, ada, flow)
    await db_session.execute(
        text(
            "UPDATE flow_runs SET updated_at = now() - interval '2 hours' WHERE id = :i"
        ),
        {"i": old},
    )
    await db_session.commit()

    assert (
        await flow_runs.fail_stale_runs(
            db_session, now=datetime.now(UTC), abandoned_after=timedelta(minutes=10)
        )
        == 1
    )
    assert await status_of(db_session, org, old) == "failed"
    assert await status_of(db_session, org, fresh) == "queued"
    run = await repo.get_run(db_session, org_id=org, run_id=old)
    assert run.error_code == "worker_stopped"


async def test_parked_schedules_do_not_starve_newer_ones(
    client, db_session, task_app, ada, monkeypatch
):
    org = await org_of(client, ada)
    await active_user(client, db_session, ada)
    flow = await simple_flow(client, ada)
    _, version = await flows.get_detail(
        db_session, org_id=org, flow_id=UUID(flow["id"])
    )
    uid = (await client.get(f"{BASE}/me", headers=ada)).json()["user"]["id"]
    monkeypatch.setattr(schedules, "BATCH", 2)
    parked = [await new_schedule(client, ada, flow) for _ in range(2)]
    newer = await new_schedule(client, ada, flow)
    for n, sid in enumerate(parked):
        run = await repo.create_run(
            db_session,
            org_id=org,
            values={
                "user_id": UUID(uid),
                "flow_id": UUID(flow["id"]),
                "flow_version_id": version.id,
                "inputs": {},
                "schedule_id": sid,
            },
        )
        await repo.set_run(db_session, org_id=org, run_id=run.id, status="waiting")
        await make_due(db_session, org, sid, minutes_ago=30 + n)
    await make_due(db_session, org, newer, minutes_ago=5)

    now = datetime.now(UTC)
    assert (
        await schedules.run_due(db_session, now=now) == 0
    )  # the parked pair fills the batch
    assert (
        await schedules.run_due(db_session, now=now) == 1
    )  # ...but no longer blocks the third
    for sid in parked:
        s = await repo.get_schedule(db_session, org_id=org, schedule_id=sid)
        assert s.next_run_at > now


async def test_a_failure_is_counted_even_when_a_slot_in_between_was_skipped(
    client, db_session, task_app, ada, monkeypatch
):
    org = await org_of(client, ada)
    await active_user(client, db_session, ada)
    flow = await simple_flow(client, ada)
    sid = await new_schedule(client, ada, flow)

    # the test transaction freezes created_at, so the first sweep's clock is set before it
    await make_due(db_session, org, sid, minutes_ago=120)
    early = datetime.now(UTC) - timedelta(hours=1)
    assert await schedules.run_due(db_session, now=early) == 1
    run_id = (
        await db_session.execute(select(FlowRun.id).where(FlowRun.schedule_id == sid))
    ).scalar_one()
    await repo.claim_run(db_session, org_id=org, run_id=run_id)
    await make_due(db_session, org, sid, consecutive_failures=2)

    monkeypatch.setattr(
        flow_runs, "MAX_ACTIVE_RUNS", 0
    )  # the next slot is skipped (busy)
    assert await schedules.run_due(db_session, now=datetime.now(UTC)) == 0
    monkeypatch.undo()
    await repo.fail_active_run(
        db_session, org_id=org, run_id=run_id, code="step_failed"
    )
    await db_session.commit()

    await make_due(db_session, org, sid)
    await schedules.run_due(db_session, now=datetime.now(UTC))
    s = await repo.get_schedule(db_session, org_id=org, schedule_id=sid)
    assert s.paused_reason == "failures"


async def test_one_schedules_failure_bookkeeping_error_does_not_lose_the_others(
    client, db_session, task_app, ada, monkeypatch
):
    org = await org_of(client, ada)
    await active_user(client, db_session, ada)
    flow = await simple_flow(client, ada)
    sids = [await new_schedule(client, ada, flow) for _ in range(2)]
    for sid in sids:
        await make_due(db_session, org, sid)
    started: list[UUID] = []

    async def refuse(db, **kw):
        started.append(kw["schedule_id"])
        raise ValueError("boom")

    real_update = repo.update_schedule
    broken = {"n": 0}

    async def flaky(db, **kw):
        if started and "consecutive_failures" in kw["values"] and not broken["n"]:
            broken["n"] += 1
            raise RuntimeError("db hiccup")
        await real_update(db, **kw)

    monkeypatch.setattr(flow_runs, "start_run", refuse)
    monkeypatch.setattr(repo, "update_schedule", flaky)
    await schedules.run_due(db_session, now=datetime.now(UTC))
    assert sorted(started) == sorted(sids)  # the second slot still got its turn


async def test_fan_out_stops_starting_children_once_the_parent_is_cancelled(
    client, db_session, task_app, ada, monkeypatch
):
    org = await org_of(client, ada)
    child = await simple_flow(client, ada)
    parent_id = await queue_run(client, ada, child)
    parent = await repo.get_run(db_session, org_id=org, run_id=parent_id)
    real = flow_runs.start_run

    async def start_then_cancel(db, **kw):
        out = await real(db, **kw)
        if await status_of(db, org, parent_id) == "queued":
            await flow_runs.cancel_run(db, org_id=org, run_id=parent_id)
        return out

    monkeypatch.setattr(flow_runs, "start_run", start_then_cancel)
    items = [{"n": str(k)} for k in range(3)]
    runs = await flow_runs.fan_out(
        db_session,
        parent=parent,
        flow_id=UUID(child["id"]),
        items=items,
        daily_quota=99,
    )
    kids = (
        await db_session.execute(
            select(func.count(FlowRun.id)).where(FlowRun.parent_run_id == parent_id)
        )
    ).scalar_one()
    assert len(runs) == kids == 1


async def test_resume_loses_to_a_worker_that_touched_the_run_in_between(
    client, db_session, task_app, ada, monkeypatch
):
    org = await org_of(client, ada)
    uid = UUID((await client.get(f"{BASE}/me", headers=ada)).json()["user"]["id"])
    flow = await simple_flow(client, ada)
    run_id = await queue_run(client, ada, flow)
    await repo.claim_run(db_session, org_id=org, run_id=run_id)
    await db_session.execute(
        text(
            "UPDATE flow_runs SET updated_at = now() - interval '2 hours' WHERE id = :i"
        ),
        {"i": run_id},
    )
    await db_session.commit()
    real = repo.reset_unfinished_steps

    async def reset_after_a_heartbeat(db, **kw):
        await repo.touch_run(
            db, org_id=org, run_id=run_id
        )  # the original worker is alive
        await real(db, **kw)

    monkeypatch.setattr(repo, "reset_unfinished_steps", reset_after_a_heartbeat)
    with pytest.raises(Conflict):
        await flow_runs.resume_run(
            db_session, org_id=org, user_id=uid, run_id=run_id,
            stale_after=timedelta(minutes=1),
        )  # fmt: skip
    assert await status_of(db_session, org, run_id) == "running"
