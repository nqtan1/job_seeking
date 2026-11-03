"""Flows and runs (ADR 0031): the engine's isolation, branching, failure and resume, and tenancy."""

from uuid import UUID, uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway, TextPart
from recruitai.ai.prompts import helper
from recruitai.modules.agents import engine, flows, runner
from recruitai.modules.agents.schemas import OutputSpec
from tests.integration.test_agents import _create as agent

BASE = "/api/v1"
TEXT = runner.output_model(OutputSpec(kind="text"))


def feature_of(a: dict) -> str:
    return helper.feature(a["id"], a["current_version"], a["spec"]["model_tier"])


def agent_node(a: dict) -> dict:
    return {
        "type": "agent",
        "id": str(uuid4()),
        "agent_id": a["id"],
        "agent_version_id": a["version_id"],
    }


def edge(src: dict, dst: dict, mapping: dict[str, str], port: str = "out") -> dict:
    return {
        "id": str(uuid4()),
        "from": {"node": src["id"], "port": port},
        "to": dst["id"],
        "map": [{"input": k, "value": v} for k, v in mapping.items()],
    }


def input_node(*names: str) -> dict:
    return {
        "type": "input",
        "id": str(uuid4()),
        "fields": [{"name": n, "label": n} for n in names],
    }


def output_node(*names: str) -> dict:
    return {
        "type": "output",
        "id": str(uuid4()),
        "fields": [{"name": n, "label": n} for n in names],
    }


async def make_flow(
    client: httpx.AsyncClient, who, nodes: list[dict], edges: list[dict]
) -> dict:
    r = await client.post(
        f"{BASE}/flows",
        headers=who,
        json={"name": "F", "graph": {"nodes": nodes, "edges": edges}},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def org_of(client: httpx.AsyncClient, who) -> UUID:
    return UUID((await client.get(f"{BASE}/me", headers=who)).json()["active_org_id"])


async def run_now(
    client, db: AsyncSession, llm, who, flow, inputs, org: UUID, job_id=None
) -> dict:
    r = await client.post(
        f"{BASE}/flows/{flow['id']}/runs",
        headers=who,
        json={"inputs": inputs, "job_id": job_id},
    )
    assert r.status_code == 202, r.text
    await engine.execute(db, llm, org_id=org, run_id=UUID(r.json()["id"]))
    return (await client.get(f"{BASE}/flow-runs/{r.json()['id']}", headers=who)).json()


def sent_text(call) -> str:
    return " ".join(p.text for p in call.parts if isinstance(p, TextPart))


async def test_a_run_moves_data_only_along_edges_even_for_two_copies_of_one_helper(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    org = await org_of(client, ada)
    x, y = await agent(client, ada, "X"), await agent(client, ada, "Y")
    i, a1, a2, c, o = (
        input_node("n"),
        agent_node(x),
        agent_node(x),
        agent_node(y),
        output_node("one", "two", "three"),
    )
    flow = await make_flow(
        client, ada, [i, a1, a2, c, o],
        [
            edge(i, a1, {"notes": "{{n}}"}), edge(i, a2, {"notes": "{{n}}"}), edge(i, c, {"notes": "{{n}}"}),
            edge(a1, o, {"one": "{{text}}"}), edge(a2, o, {"two": "{{text}}"}), edge(c, o, {"three": "{{text}}"}),
        ],
    )  # fmt: skip
    fake_llm.queue(feature_of(x), TEXT(text="CANARY-from-first-copy"))
    fake_llm.queue(feature_of(x), TEXT(text="second copy"))
    fake_llm.queue(feature_of(y), TEXT(text="other helper"))

    run = await run_now(client, db_session, fake_llm, ada, flow, {"n": "hello"}, org)

    assert run["status"] == "done"
    assert run["result"] == {
        "one": "CANARY-from-first-copy",
        "two": "second copy",
        "three": "other helper",
    }
    assert [s["status"] for s in run["steps"]] == ["done"] * 5
    # the canary reached the output and nowhere else: not the other copy, not the other helper
    for call in fake_llm.calls:
        assert "CANARY" not in sent_text(call) and "hello" in sent_text(call)
    assert {h["to_node"] for h in run["handoffs"]} >= {
        a1["id"],
        a2["id"],
        c["id"],
        o["id"],
    }
    first = next(
        h
        for h in run["handoffs"]
        if h["from_node"] == i["id"] and h["to_node"] == a1["id"]
    )
    assert first["payload"] == {"notes": "hello"} and first["truncated"] is False


async def test_a_condition_takes_one_branch_and_skips_the_other_without_a_model_call(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    org = await org_of(client, ada)
    x = await agent(client, ada)
    i = input_node("n")
    cond = {
        "type": "condition",
        "id": str(uuid4()),
        "op": "contains",
        "value": "urgent",
    }
    yes, no, o = (
        agent_node(x),
        {"type": "transform", "id": str(uuid4()), "op": "upper"},
        output_node("a", "b"),
    )
    flow = await make_flow(
        client, ada, [i, cond, yes, no, o],
        [
            edge(i, cond, {"value": "{{n}}"}),
            edge(cond, yes, {"notes": "{{value}}"}, "true"), edge(cond, no, {"text": "{{value}}"}, "false"),
            edge(yes, o, {"a": "{{text}}"}), edge(no, o, {"b": "{{text}}"}),
        ],
    )  # fmt: skip
    fake_llm.queue(feature_of(x), TEXT(text="handled"))

    urgent = await run_now(
        client, db_session, fake_llm, ada, flow, {"n": "URGENT call"}, org
    )
    assert urgent["result"] == {"a": "handled", "b": ""}
    skipped = [s["status"] for s in urgent["steps"] if s["node_id"] == no["id"]]
    assert skipped == ["skipped"] and len(fake_llm.calls) == 1

    calm = await run_now(client, db_session, fake_llm, ada, flow, {"n": "no rush"}, org)
    assert (
        calm["result"] == {"a": "", "b": "NO RUSH"} and len(fake_llm.calls) == 1
    )  # no new call


async def test_a_failed_step_keeps_finished_work_and_resume_runs_only_what_is_left(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada, bob
):
    org = await org_of(client, ada)
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )

    failed = await run_now(
        client, db_session, fake_llm, ada, flow, {"n": "hi"}, org
    )  # nothing queued: the model "breaks"
    assert failed["status"] == "failed" and failed["error_code"] == "step_failed"
    by_node = {s["node_id"]: s for s in failed["steps"]}
    assert (
        by_node[i["id"]]["status"],
        by_node[a["id"]]["status"],
        by_node[o["id"]]["status"],
    ) == ("done", "failed", "pending")
    assert "AssertionError" not in str(failed)  # never exception text

    assert (
        await client.post(f"{BASE}/flow-runs/{failed['id']}/resume", headers=bob)
    ).status_code == 404
    fake_llm.queue(feature_of(x), TEXT(text="fixed"))
    resumed = await client.post(f"{BASE}/flow-runs/{failed['id']}/resume", headers=ada)
    assert resumed.status_code == 202 and resumed.json()["status"] == "queued"
    await engine.execute(db_session, fake_llm, org_id=org, run_id=UUID(failed["id"]))

    done = (await client.get(f"{BASE}/flow-runs/{failed['id']}", headers=ada)).json()
    assert (
        done["status"] == "done"
        and done["result"] == {"r": "fixed"}
        and done["error_code"] is None
    )
    assert len(fake_llm.calls) == 2  # the first try, and one retry of that step only
    assert (
        await client.post(f"{BASE}/flow-runs/{failed['id']}/resume", headers=ada)
    ).status_code == 409

    again = len(
        fake_llm.calls
    )  # a duplicate delivery of the finished task does nothing
    await engine.execute(db_session, fake_llm, org_id=org, run_id=UUID(failed["id"]))
    assert len(fake_llm.calls) == again


async def test_unsafe_runs_fail_loudly_cancel_works_and_two_live_edges_are_refused(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    org = await org_of(client, ada)
    i = input_node("n")
    cond = {"type": "condition", "id": str(uuid4()), "op": "gt", "value": "5"}
    o = output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, cond, o],
        [edge(i, cond, {"value": "{{n}}"}), edge(cond, o, {"r": "{{value}}"}, "true")],
    )
    bad = await run_now(client, db_session, fake_llm, ada, flow, {"n": "lots"}, org)
    assert (
        bad["status"] == "failed" and bad["error_code"] == "condition_invalid"
    )  # never a silent wrong branch

    t1, t2 = (
        {"type": "transform", "id": str(uuid4()), "op": "trim"},
        {"type": "transform", "id": str(uuid4()), "op": "trim"},
    )
    clash = await make_flow(
        client, ada, [i, t1, t2, o],
        [edge(i, t1, {"text": "{{n}}"}), edge(i, t2, {"text": "{{n}}"}), edge(t1, o, {"r": "{{text}}"}), edge(t2, o, {"r": "{{text}}"})],
    )  # fmt: skip
    assert [x["code"] for x in clash["issues"]] == [
        "shared_input"
    ]  # refused before any AI is spent
    refused = await client.post(
        f"{BASE}/flows/{clash['id']}/runs", headers=ada, json={"inputs": {"n": "x"}}
    )
    assert refused.status_code == 422

    ok = await make_flow(
        client,
        ada,
        [i, t1, o],
        [edge(i, t1, {"text": "{{n}}"}), edge(t1, o, {"r": "{{text}}"})],
    )
    queued = await client.post(
        f"{BASE}/flows/{ok['id']}/runs", headers=ada, json={"inputs": {"n": "x"}}
    )
    cancelled = await client.post(
        f"{BASE}/flow-runs/{queued.json()['id']}/cancel", headers=ada
    )
    assert cancelled.json()["status"] == "cancelled"
    await engine.execute(
        db_session, fake_llm, org_id=org, run_id=UUID(queued.json()["id"])
    )
    final = (
        await client.get(f"{BASE}/flow-runs/{queued.json()['id']}", headers=ada)
    ).json()
    assert final["status"] == "cancelled" and all(
        s["status"] == "pending" for s in final["steps"]
    )
    assert (
        await client.post(f"{BASE}/flow-runs/{queued.json()['id']}/cancel", headers=ada)
    ).status_code == 409


async def test_starting_a_run_validates_everything_and_stays_in_the_tenant(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada, bob
):
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    url = f"{BASE}/flows/{flow['id']}"

    assert flow["max_ai_calls"] == 1 and flow["issues"] == []
    for method, path, body in (
        ("get", url, None), ("patch", url, {"name": "x"}), ("delete", url, None),
        ("get", f"{url}/versions", None), ("get", f"{url}/runs", None),
        ("post", f"{url}/runs", {"inputs": {"n": "x"}}),
        ("post", f"{url}/versions", {"based_on": 1, "graph": flow["graph"]}),
    ):  # fmt: skip
        assert (
            await client.request(method, path, headers=bob, json=body)
        ).status_code == 404, path
    assert (await client.get(f"{BASE}/flows", headers=bob)).json() == []

    # bob cannot wire ada's helper into his own flow: it reads as "unavailable" and refuses to run
    forged = await make_flow(
        client,
        bob,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    assert [x["code"] for x in forged["issues"]] == ["agent_unavailable"]
    refused = await client.post(
        f"{BASE}/flows/{forged['id']}/runs", headers=bob, json={"inputs": {"n": "x"}}
    )
    assert refused.status_code == 422

    assert (
        await client.post(f"{url}/runs", headers=ada, json={"inputs": {}})
    ).status_code == 422  # required input
    assert (
        await client.post(
            f"{url}/runs", headers=ada, json={"inputs": {"n": "x", "z": "y"}}
        )
    ).status_code == 422
    assert (
        await client.post(
            f"{url}/runs",
            headers=ada,
            json={"inputs": {"n": "x"}, "job_id": str(uuid4())},
        )
    ).status_code == 404

    first = await client.post(
        f"{url}/runs", headers=ada, json={"inputs": {"n": "x"}}, params={}
    )
    key = {"Idempotency-Key": "once", **ada}
    one = await client.post(f"{url}/runs", headers=key, json={"inputs": {"n": "x"}})
    two = await client.post(f"{url}/runs", headers=key, json={"inputs": {"n": "x"}})
    assert (one.status_code, two.status_code) == (202, 200) and one.json()[
        "id"
    ] == two.json()["id"]
    assert first.status_code == 202
    third = await client.post(f"{url}/runs", headers=ada, json={"inputs": {"n": "x"}})
    assert third.status_code == 409  # two runs are already live

    archived = await client.delete(f"{BASE}/agents/{x['id']}", headers=ada)
    assert archived.status_code == 204
    detail = (await client.get(url, headers=ada)).json()
    assert (
        detail["issues"] == []
    )  # a pinned version is immutable: archiving never breaks its flows


async def test_flow_versions_never_overwrite_and_the_editor_preview_matches_the_engine(
    client, ada
):
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    nodes, edges = (
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    flow = await make_flow(client, ada, nodes, edges)
    url = f"{BASE}/flows/{flow['id']}"

    draft = {
        "nodes": nodes,
        "edges": edges[:1],
    }  # work in progress is saved, with its problems shown
    v2 = await client.post(
        f"{url}/versions", headers=ada, json={"based_on": 1, "graph": draft}
    )
    assert v2.status_code == 201 and v2.json()["version"] == 2
    assert (
        await client.post(
            f"{url}/versions", headers=ada, json={"based_on": 1, "graph": draft}
        )
    ).status_code == 409
    assert {
        x["code"] for x in (await client.get(url, headers=ada)).json()["issues"]
    } >= {"unreachable"}
    check = (
        await client.post(f"{BASE}/flows/validate", headers=ada, json={"graph": draft})
    ).json()
    assert check["ok"] is False and check["max_ai_calls"] == 1

    dup = {"nodes": nodes + [nodes[0]], "edges": edges}
    assert (
        await client.post(
            f"{url}/versions", headers=ada, json={"based_on": 2, "graph": dup}
        )
    ).status_code == 422

    preview = await client.post(
        f"{BASE}/flows/preview-handoff", headers=ada,
        json={"map": [{"input": "a", "value": "Hi {{who}}"}], "outputs": {"who": "Ada", "secret": "S"}},
    )  # fmt: skip
    assert preview.json() == {
        "values": {"a": {"text": "Hi Ada", "chars": 6}},
        "truncated": False,
    }


async def test_a_run_goes_through_the_real_worker_and_old_runs_are_swept(
    real_client, db_engine, task_app, fake_llm, users, monkeypatch
):
    ada, bob = users["ada"], users["bob"]
    monkeypatch.setattr(
        "recruitai.ai.dependencies.build_llm_gateway", lambda *a, **k: fake_llm
    )
    x = await agent(real_client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        real_client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    fake_llm.queue(feature_of(x), TEXT(text="via worker"))

    accepted = await real_client.post(
        f"{BASE}/flows/{flow['id']}/runs", headers=ada, json={"inputs": {"n": "hi"}}
    )
    assert accepted.status_code == 202
    run_url = f"{BASE}/flow-runs/{accepted.json()['id']}"
    assert (await real_client.get(run_url, headers=ada)).json()["status"] == "queued"
    assert (await real_client.get(run_url, headers=bob)).status_code == 404

    await task_app.run_worker_async(wait=False, install_signal_handlers=False)

    run = (await real_client.get(run_url, headers=ada)).json()
    assert run["status"] == "done" and run["result"] == {"r": "via worker"}
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE flow_runs SET created_at = now() - interval '40 days'")
        )
    from datetime import UTC, datetime

    from recruitai.modules.privacy import service as privacy

    async with AsyncSession(db_engine, expire_on_commit=False) as s:
        assert await privacy.sweep_flow_runs(s, now=datetime.now(UTC)) >= 1
    assert (await real_client.get(run_url, headers=ada)).status_code == 404


async def test_runs_survive_dead_workers_races_and_awkward_input(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    from datetime import UTC, datetime, timedelta

    from recruitai.modules.agents import flow_repository as repo

    org = await org_of(client, ada)
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    url = f"{BASE}/flows/{flow['id']}/runs"

    # idempotency: blank keys are ignored; the same key for another request is refused, not answered
    blank = await client.post(
        url, headers={**ada, "Idempotency-Key": "  "}, json={"inputs": {"n": "a"}}
    )
    assert blank.status_code == 202
    await client.post(f"{BASE}/flow-runs/{blank.json()['id']}/cancel", headers=ada)
    key = {**ada, "Idempotency-Key": "k1"}
    first = await client.post(url, headers=key, json={"inputs": {"n": "a"}})
    assert first.status_code == 202
    assert (
        await client.post(url, headers=key, json={"inputs": {"n": "different"}})
    ).status_code == 409

    # NUL cannot be stored: refused at the edge, never a 500
    assert (
        await client.post(url, headers=ada, json={"inputs": {"n": "a\u0000b"}})
    ).status_code == 422

    # a worker that died leaves a running run: the sweep fails it, frees the slot and it can be resumed
    run_id = UUID(first.json()["id"])
    await repo.claim_run(db_session, org_id=org, run_id=run_id)
    await repo.set_run(
        db_session,
        org_id=org,
        run_id=run_id,
        updated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert (
        await client.post(f"{BASE}/flow-runs/{run_id}/resume", headers=ada)
    ).status_code == 202  # stale: allowed
    await repo.claim_run(db_session, org_id=org, run_id=run_id)
    await repo.set_run(
        db_session,
        org_id=org,
        run_id=run_id,
        updated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert (
        await flows.fail_stale_runs(
            db_session, now=datetime.now(UTC), abandoned_after=timedelta(minutes=10)
        )
        == 1
    )
    dead = (await client.get(f"{BASE}/flow-runs/{run_id}", headers=ada)).json()
    assert dead["status"] == "failed" and dead["error_code"] == "worker_stopped"

    # a healthy running run is never taken for stuck, and cancel cannot overwrite a finished run
    fake_llm.queue(feature_of(x), TEXT(text="ok"))
    resumed = await client.post(f"{BASE}/flow-runs/{run_id}/resume", headers=ada)
    assert resumed.status_code == 202
    await engine.execute(db_session, fake_llm, org_id=org, run_id=run_id)
    assert (
        await client.post(f"{BASE}/flow-runs/{run_id}/cancel", headers=ada)
    ).status_code == 409
    assert (await client.get(f"{BASE}/flow-runs/{run_id}", headers=ada)).json()[
        "status"
    ] == "done"
    assert (
        await client.post(f"{BASE}/flow-runs/{run_id}/resume", headers=ada)
    ).status_code == 409

    # model output with NUL is cleaned instead of crashing the run
    again = await client.post(url, headers=ada, json={"inputs": {"n": "b"}})
    fake_llm.queue(feature_of(x), TEXT(text="bad\u0000text"))
    await engine.execute(
        db_session, fake_llm, org_id=org, run_id=UUID(again.json()["id"])
    )
    done = (
        await client.get(f"{BASE}/flow-runs/{again.json()['id']}", headers=ada)
    ).json()
    assert done["status"] == "done" and done["result"] == {"r": "badtext"}


async def test_a_step_fed_only_by_a_branch_not_taken_is_skipped_not_failed(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    org = await org_of(client, ada)
    x = await agent(
        client,
        ada,
        spec={
            "instructions": "x",
            "inputs": [{"name": "notes", "label": "N"}, {"name": "more", "label": "M"}],
        },
    )
    i = input_node("n")
    cond = {"type": "condition", "id": str(uuid4()), "op": "contains", "value": "go"}
    a, o = agent_node(x), output_node("r")
    flow = await make_flow(
        client, ada, [i, cond, a, o],
        [edge(i, cond, {"value": "{{n}}"}), edge(i, a, {"notes": "{{n}}"}),
         edge(cond, a, {"more": "{{value}}"}, "true"), edge(a, o, {"r": "{{text}}"})],
    )  # fmt: skip
    run = await run_now(
        client, db_session, fake_llm, ada, flow, {"n": "stop"}, org
    )  # branch not taken
    assert run["status"] == "done" and run["result"] == {} and len(fake_llm.calls) == 0
    assert [s["status"] for s in run["steps"] if s["node_id"] == a["id"]] == ["skipped"]


async def test_a_worker_that_lost_its_step_cannot_overwrite_it_and_cancel_ends_the_spinner(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    from recruitai.config import Settings
    from recruitai.modules.agents import flow_repository as repo

    org = await org_of(client, ada)
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    run = (
        await client.post(
            f"{BASE}/flows/{flow['id']}/runs", headers=ada, json={"inputs": {"n": "x"}}
        )
    ).json()
    run_id = UUID(run["id"])
    await repo.claim_run(db_session, org_id=org, run_id=run_id)
    step = next(
        s
        for s in await repo.list_steps(db_session, org_id=org, run_id=run_id)
        if str(s.node_id) == a["id"]
    )
    assert await repo.claim_step(db_session, org_id=org, step_id=step.id)

    # the run is resumed under a slow worker: its step goes back to pending...
    await repo.reset_unfinished_steps(db_session, org_id=org, run_id=run_id)
    # ...so the slow worker's late answer is refused instead of overwriting the new worker's
    assert not await repo.set_step(
        db_session,
        org_id=org,
        step_id=step.id,
        only_if=("running",),
        status="done",
        output={"text": "late"},
    )

    assert await repo.claim_step(db_session, org_id=org, step_id=step.id)
    cancelled = await client.post(f"{BASE}/flow-runs/{run_id}/cancel", headers=ada)
    assert cancelled.json()["status"] == "cancelled"
    steps = (await client.get(f"{BASE}/flow-runs/{run_id}", headers=ada)).json()[
        "steps"
    ]
    assert [s["status"] for s in steps if s["node_id"] == a["id"]] == [
        "failed"
    ]  # no spinner on a cancelled run

    # a live model call is never taken for stuck: the thresholds follow the model timeout
    from recruitai.modules.agents.flows import abandoned_after, stale_after

    cfg = Settings.model_construct(ai_call_timeout_s=120.0)
    assert (
        stale_after(cfg).total_seconds() == 300
        and abandoned_after(cfg).total_seconds() == 600
    )


async def test_the_editor_preview_is_rate_limited(client, ada):
    body = {"map": [{"input": "a", "value": "{{x}}"}], "outputs": {"x": "y"}}
    codes = [
        (
            await client.post(f"{BASE}/flows/preview-handoff", headers=ada, json=body)
        ).status_code
        for _ in range(125)
    ]
    assert (
        codes[:120] == [200] * 120 and codes[120:] == [429] * 5
    )  # 120 a minute, then refused


async def test_the_editor_preview_refuses_a_huge_sample(client, ada):
    huge = {"map": [], "outputs": {"x": "y" * 90_000}}
    assert (
        await client.post(f"{BASE}/flows/preview-handoff", headers=ada, json=huge)
    ).status_code == 422


def test_the_next_slot_follows_the_local_clock_daylight_saving_included():
    from datetime import UTC, datetime

    from recruitai.modules.agents.schedules import next_run

    t = lambda *a: datetime(*a, tzinfo=UTC)
    # Paris is UTC+1 in November: 08:30 local = 07:30 UTC, today if still ahead, else tomorrow
    assert next_run("daily", "08:30", None, "Europe/Paris", t(2026, 11, 3, 6, 0)) == t(
        2026, 11, 3, 7, 30
    )
    assert next_run("daily", "08:30", None, "Europe/Paris", t(2026, 11, 3, 7, 30)) == t(
        2026, 11, 4, 7, 30
    )
    # ...and UTC+2 in summer
    assert next_run("daily", "08:30", None, "Europe/Paris", t(2026, 7, 1, 0, 0)) == t(
        2026, 7, 1, 6, 30
    )
    # weekly: Monday 09:00 Paris (2026-11-03 is a Tuesday)
    assert next_run("weekly", "09:00", 0, "Europe/Paris", t(2026, 11, 3, 12, 0)) == t(
        2026, 11, 9, 8, 0
    )
    assert next_run("hourly", None, None, "UTC", t(2026, 11, 3, 10, 42)) == t(
        2026, 11, 3, 11, 0
    )


async def test_schedules_are_validated_like_a_run_private_and_capped(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada, bob
):
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    url = f"{BASE}/flows/{flow['id']}/schedules"
    daily = {
        "cadence": "daily",
        "at_time": "08:00",
        "timezone": "Europe/Paris",
        "inputs": {"n": "hello"},
    }

    made = await client.post(url, headers=ada, json=daily)
    assert (
        made.status_code == 201
        and made.json()["enabled"]
        and made.json()["next_run_at"]
    )
    sid = made.json()["id"]
    assert [s["id"] for s in (await client.get(url, headers=ada)).json()] == [sid]

    bad = {
        "no time": {**daily, "at_time": None},
        "weekly without a day": {**daily, "cadence": "weekly"},
        "hourly with a time": {**daily, "cadence": "hourly"},
        "unknown zone": {**daily, "timezone": "Mars/Base"},
        "missing input": {**daily, "inputs": {}},
        "unknown input": {**daily, "inputs": {"n": "x", "z": "y"}},
        "bad time": {**daily, "at_time": "25:99"},
        "unknown zone, hourly": {
            "cadence": "hourly",
            "timezone": "Mars/Base",
            "inputs": {"n": "x"},
        },
    }
    for label, body in bad.items():
        assert (await client.post(url, headers=ada, json=body)).status_code == 422, (
            label
        )

    for _ in range(4):  # up to 5 per account
        assert (await client.post(url, headers=ada, json=daily)).status_code == 201
    assert (await client.post(url, headers=ada, json=daily)).status_code == 422

    paused = await client.patch(
        f"{BASE}/schedules/{sid}", headers=ada, json={"enabled": False}
    )
    assert paused.json()["enabled"] is False
    for method, path, body in (
        ("get", url, None), ("post", url, daily),
        ("patch", f"{BASE}/schedules/{sid}", {"enabled": True}), ("delete", f"{BASE}/schedules/{sid}", None),
    ):  # fmt: skip
        assert (
            await client.request(method, path, headers=bob, json=body)
        ).status_code == 404, path
    assert (
        await client.delete(f"{BASE}/schedules/{sid}", headers=ada)
    ).status_code == 204
    assert (
        await client.delete(f"{BASE}/schedules/{sid}", headers=ada)
    ).status_code == 404


async def test_due_schedules_start_once_per_slot_and_stop_when_they_should(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from recruitai.modules.agents import flow_repository as repo
    from recruitai.modules.agents import schedules

    org = await org_of(client, ada)
    uid = (await client.get(f"{BASE}/me", headers=ada)).json()["user"]["id"]
    await db_session.execute(
        text("UPDATE users SET last_active_at = now() WHERE id = :u"), {"u": uid}
    )
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    body = {"cadence": "hourly", "timezone": "UTC", "inputs": {"n": "hi"}}
    sid = UUID(
        (
            await client.post(
                f"{BASE}/flows/{flow['id']}/schedules", headers=ada, json=body
            )
        ).json()["id"]
    )

    async def due(minutes_ago=5):
        await repo.update_schedule(
            db_session,
            org_id=org,
            schedule_id=sid,
            values={"next_run_at": datetime.now(UTC) - timedelta(minutes=minutes_ago)},
        )
        await db_session.commit()

    async def runs():
        return (
            await client.get(f"{BASE}/flow-runs?flow_id={flow['id']}", headers=ada)
        ).json()

    now = datetime.now(UTC)
    assert await schedules.run_due(db_session, now=now) == 0  # not due yet
    await due()
    assert await schedules.run_due(db_session, now=now) == 1
    first = (await runs())[0]
    assert first["trigger"] == "schedule" and first["status"] == "queued"
    s = await repo.get_schedule(db_session, org_id=org, schedule_id=sid)
    assert (
        s.next_run_at > now and s.last_run_at is not None
    )  # the next slot is saved, nothing is replayed
    assert await schedules.run_due(db_session, now=now) == 0

    # the same slot can never start twice, even if the slot is claimed again (crash, duplicate sweep)
    slot = now - timedelta(minutes=5)
    await repo.update_schedule(
        db_session, org_id=org, schedule_id=sid, values={"next_run_at": slot}
    )
    await db_session.commit()
    await schedules.run_due(db_session, now=now)
    assert len(await runs()) == 1

    # three failed scheduled runs in a row pause the schedule instead of spending forever
    run_id = UUID(first["id"])
    await repo.claim_run(db_session, org_id=org, run_id=run_id)
    await repo.fail_active_run(
        db_session, org_id=org, run_id=run_id, code="step_failed"
    )
    await repo.update_schedule(
        db_session, org_id=org, schedule_id=sid, values={"consecutive_failures": 2}
    )
    await due()
    assert await schedules.run_due(db_session, now=now) == 0
    s = await repo.get_schedule(db_session, org_id=org, schedule_id=sid)
    assert s.paused_reason == "failures"
    resumed = await client.patch(
        f"{BASE}/schedules/{sid}", headers=ada, json={"enabled": True}
    )
    assert (
        resumed.json()["paused_reason"] is None
    )  # turning it back on clears the pause

    # a dormant account stops costing anything
    await db_session.execute(
        text(
            "UPDATE users SET last_active_at = now() - interval '45 days' WHERE id = :u"
        ),
        {"u": uid},
    )
    await due()
    assert await schedules.run_due(db_session, now=now) == 0
    s = await repo.get_schedule(db_session, org_id=org, schedule_id=sid)
    assert s.paused_reason == "inactive"


async def test_all_runs_can_be_filtered_paged_and_run_again(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada, bob
):
    org = await org_of(client, ada)
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    fake_llm.queue(feature_of(x), TEXT(text="ok"))
    done = await run_now(client, db_session, fake_llm, ada, flow, {"n": "first"}, org)
    failed = await run_now(
        client, db_session, fake_llm, ada, flow, {"n": "second"}, org
    )  # nothing queued: fails
    assert (done["status"], failed["status"]) == ("done", "failed")

    everything = (await client.get(f"{BASE}/flow-runs", headers=ada)).json()
    assert [r["id"] for r in everything] == [failed["id"], done["id"]]  # newest first
    assert {r["flow_name"] for r in everything} == {"F"} and everything[0][
        "trigger"
    ] == "manual"
    only_failed = (
        await client.get(f"{BASE}/flow-runs?status=failed", headers=ada)
    ).json()
    assert [r["id"] for r in only_failed] == [failed["id"]]
    older = (
        await client.get(
            f"{BASE}/flow-runs",
            headers=ada,
            params={"before_id": everything[0]["id"]},
        )
    ).json()
    assert [r["id"] for r in older] == [done["id"]]
    assert (
        await client.get(f"{BASE}/flow-runs?status=weird", headers=ada)
    ).status_code == 422
    assert (await client.get(f"{BASE}/flow-runs", headers=bob)).json() == []  # private

    again = await client.post(f"{BASE}/flow-runs/{done['id']}/rerun", headers=ada)
    assert again.status_code == 202 and again.json()["id"] != done["id"]
    fresh = (
        await client.get(f"{BASE}/flow-runs/{again.json()['id']}", headers=ada)
    ).json()
    assert fresh["inputs"] == {"n": "first"}  # the same inputs
    assert (
        await client.post(f"{BASE}/flow-runs/{done['id']}/rerun", headers=bob)
    ).status_code == 404


async def test_a_schedule_that_cannot_start_pauses_instead_of_retrying_forever(
    client, db_session, fake_llm: FakeLLMGateway, task_app, ada
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from recruitai.modules.agents import flow_repository as repo
    from recruitai.modules.agents import schedules

    org = await org_of(client, ada)
    uid = (await client.get(f"{BASE}/me", headers=ada)).json()["user"]["id"]
    await db_session.execute(
        text("UPDATE users SET last_active_at = now() WHERE id = :u"), {"u": uid}
    )
    x = await agent(client, ada)
    i, a, o = input_node("n"), agent_node(x), output_node("r")
    flow = await make_flow(
        client,
        ada,
        [i, a, o],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, o, {"r": "{{text}}"})],
    )
    body = {"cadence": "hourly", "timezone": "UTC", "inputs": {"n": "hi"}}
    sid = UUID(
        (
            await client.post(
                f"{BASE}/flows/{flow['id']}/schedules", headers=ada, json=body
            )
        ).json()["id"]
    )
    await client.delete(
        f"{BASE}/flows/{flow['id']}", headers=ada
    )  # the flow is archived: every start is refused

    for _ in range(3):
        await repo.update_schedule(
            db_session,
            org_id=org,
            schedule_id=sid,
            values={"next_run_at": datetime.now(UTC) - timedelta(minutes=1)},
        )
        await db_session.commit()
        await schedules.run_due(db_session, now=datetime.now(UTC))
    s = await repo.get_schedule(db_session, org_id=org, schedule_id=sid)
    assert (
        s.paused_reason == "failures" and s.consecutive_failures == 3
    )  # not reset by the refusals
    # it cannot be switched back on while the flow cannot run
    assert (
        await client.patch(
            f"{BASE}/schedules/{sid}", headers=ada, json={"enabled": True}
        )
    ).status_code == 409
