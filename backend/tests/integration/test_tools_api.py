"""/api/v1/tools (ADR 0039, 0043): the catalogue of the packs that are on, the tools service's
health, and "Try it" on the Tools page."""

from dataclasses import replace

import httpx

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.jobs import PROMPT_VERSION
from recruitai.config import get_settings
from recruitai.core import tools
from tests.unit.test_jobs_parser import blank_job


async def test_get_tools_lists_the_packs_that_are_on(
    client: httpx.AsyncClient, emulator_token, monkeypatch
):
    ada = {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}
    r = await client.get("/api/v1/tools", headers=ada)
    assert r.status_code == 200
    by_id = {t["id"]: t for t in r.json()}
    # chat only: no flow step
    assert set(by_id) == {i for i, t in tools.all().items() if not t.chat_only}
    assert by_id["send_email"] == {
        "id": "send_email",
        "pack": "messages",
        "inputs": [
            {"name": "to", "required": True},
            {"name": "subject", "required": True},
            {"name": "body", "required": True},
        ],
        "outputs": ["status"],
        "effect": "outside",
        "ai_uses": 0,
        "daily_cap": 20,
        "needs_job": False,
        "chat": False,
        "page": None,
        "mcp": False,
    }

    # a pack behind a Settings flag (here the web pack, behind radar_enabled) disappears when it is off
    web = {
        k: replace(t, flag="radar_enabled")
        for k, t in tools.all().items()
        if t.pack == "web"
    }
    monkeypatch.setattr(tools, "_TOOLS", {**tools.all(), **web})
    off = get_settings().model_copy(update={"radar_enabled": False})
    client._transport.app.dependency_overrides[get_settings] = lambda: off  # type: ignore[attr-defined]
    r = await client.get("/api/v1/tools", headers=ada)
    assert {t["pack"] for t in r.json()} == {"career", "core", "messages"}
    client._transport.app.dependency_overrides.pop(get_settings)  # type: ignore[attr-defined]


async def test_try_runs_an_agent_tool_for_real_for_its_account_only(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    url = "/api/v1/tools/{}/try"
    note = {"inputs": {"title": "Lyon offers", "body": "Three to read."}}
    r = await client.post(url.format("save_note"), headers=ada, json=note)
    assert r.status_code == 200
    assert (
        r.json()["remote"] is False
    )  # no TOOLS_URL here: the same handler, in-process
    note_id = r.json()["outputs"]["note_id"]
    assert (
        await client.get(f"/api/v1/notes/{note_id}", headers=ada)
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/notes/{note_id}", headers=bob)
    ).status_code == 404

    fake_llm.queue(PROMPT_VERSION, blank_job())
    job = (await client.post("/api/v1/jobs", headers=bob, json={"source": "manual", "text": "Dev"})).json()  # fmt: skip
    lookup = url.format("job_lookup")
    r = await client.post(lookup, headers=ada, json={"job_id": job["id"]})
    assert r.status_code == 404  # another account's job is never read
    r = await client.post(lookup, headers=bob, json={"job_id": job["id"]})
    assert set(r.json()["outputs"]) == set(tools.get("job_lookup").outputs)

    # only what an agent can use; inputs are the tool's own; a job tool needs a job
    for tool in ("send_email", "remember", "nope"):
        assert (
            await client.post(url.format(tool), headers=ada, json={})
        ).status_code == 404
    bad = [
        ("save_note", {"inputs": {"title": "T"}}),
        ("save_note", {"inputs": {"title": "T", "body": "B", "secret": "x"}}),
        ("job_lookup", {}),
    ]
    for tool, body in bad:
        assert (
            await client.post(url.format(tool), headers=ada, json=body)
        ).status_code == 422
    assert (await client.post(url.format("save_note"), json=note)).status_code == 401


async def test_status_says_tools_run_in_process_without_a_service(
    client: httpx.AsyncClient, ada
):
    r = await client.get("/api/v1/tools/status", headers=ada)
    assert r.json() == {"remote": False, "ok": True, "served": None, "latency_ms": 0}
