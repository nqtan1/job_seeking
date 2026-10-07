"""/api/v1/coach through real HTTP incl. the SSE stream (P2-23d)."""

import json

import httpx
import pytest
from fastapi import FastAPI

from recruitai.ai.gateway import FakeLLMGateway, QuotaExceeded
from recruitai.ai.prompts.coach import PROMPT_VERSION
from recruitai.core.app_check import verify_app_check
from recruitai.core.errors import UpstreamUnavailable
from tests.integration.test_matching_router import _add_job, _add_profile

BASE = "/api/v1/coach/conversations"


@pytest.fixture
def ada(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}


@pytest.fixture
def bob(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-bob', 'bob@example.com')}"}


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def _conversation(client: httpx.AsyncClient, llm: FakeLLMGateway, who) -> str:
    await _add_profile(client, llm, who)
    job_id = await _add_job(client, llm, who)
    resp = await client.post(BASE, headers=who, json={"job_id": job_id})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_stream_a_reply_then_read_the_stored_turn(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    conv_id = await _conversation(client, fake_llm, ada)
    fake_llm.queue_stream(PROMPT_VERSION, ["Votre ", "CV ", "est solide."])

    resp = await client.post(
        f"{BASE}/{conv_id}/messages",
        headers=ada,
        json={"content": "Que penses-tu de mon CV ?"},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    events = parse_sse(resp.text)
    assert events == [
        ("token", {"text": "Votre "}), ("token", {"text": "CV "}),
        ("token", {"text": "est solide."}), ("done", {}),
    ]  # fmt: skip

    stored = (await client.get(f"{BASE}/{conv_id}/messages", headers=ada)).json()
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", "Que penses-tu de mon CV ?"),
        ("assistant", "Votre CV est solide."),
    ]


async def test_refusals_and_first_chunk_errors_are_problem_json_not_a_stream(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    conv_id = await _conversation(client, fake_llm, ada)
    url = f"{BASE}/{conv_id}/messages"
    calls = len(fake_llm.calls)

    assert (
        await client.post(url, headers=ada, json={"content": ""})
    ).status_code == 422
    too_long = await client.post(url, headers=ada, json={"content": "x" * 4001})
    assert too_long.status_code == 422
    unknown = await client.post(
        f"{BASE}/00000000-0000-0000-0000-000000000000/messages",
        headers=ada,
        json={"content": "hi"},
    )
    assert unknown.status_code == 404
    assert len(fake_llm.calls) == calls  # none of these reached the model

    fake_llm.queue_stream(PROMPT_VERSION, [], error=QuotaExceeded())
    over = await client.post(url, headers=ada, json={"content": "hi"})
    assert over.status_code == 429 and over.headers["content-type"].startswith(
        "application/problem+json"
    )
    assert over.json()["code"] == "quota_exceeded"

    fake_llm.queue_stream(
        PROMPT_VERSION, [], error=UpstreamUnavailable("down", code="ai_unavailable")
    )
    down = await client.post(url, headers=ada, json={"content": "hi"})
    assert down.status_code == 503 and down.json()["code"] == "ai_unavailable"

    assert (
        await client.get(f"{BASE}/{conv_id}/messages", headers=ada)
    ).json() == []  # nothing stored


async def test_an_error_after_the_first_token_ends_the_stream_with_an_error_event(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    conv_id = await _conversation(client, fake_llm, ada)
    fake_llm.queue_stream(
        PROMPT_VERSION,
        ["Bon"],
        error=UpstreamUnavailable("The AI provider timed out.", code="ai_timeout"),
    )

    resp = await client.post(
        f"{BASE}/{conv_id}/messages", headers=ada, json={"content": "Salut"}
    )

    assert resp.status_code == 200  # the stream had already started
    events = parse_sse(resp.text)
    assert events[0] == ("token", {"text": "Bon"})
    assert events[-1] == (
        "error",
        {"code": "ai_timeout", "detail": "The AI provider timed out."},
    )
    assert [name for name, _ in events].count("done") == 0 and len(events) == 2
    assert (await client.get(f"{BASE}/{conv_id}/messages", headers=ada)).json() == []

    # an unexpected bug mid-stream is reported generically, never with its text
    fake_llm.queue_stream(
        PROMPT_VERSION, ["Bon"], error=RuntimeError("secret internals")
    )
    crashed = await client.post(
        f"{BASE}/{conv_id}/messages", headers=ada, json={"content": "Salut"}
    )
    assert "secret" not in crashed.text
    assert parse_sse(crashed.text)[-1][1]["code"] == "internal_error"


async def test_org_b_cannot_stream_read_or_open_a_conversation_on_org_as_data(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    conv_id = await _conversation(client, fake_llm, ada)
    ada_job = (await client.get("/api/v1/jobs", headers=ada)).json()[0]["id"]
    await _add_profile(client, fake_llm, bob)
    calls = len(fake_llm.calls)

    stream = await client.post(
        f"{BASE}/{conv_id}/messages", headers=bob, json={"content": "hi"}
    )
    assert stream.status_code == 404
    assert (
        await client.get(f"{BASE}/{conv_id}/messages", headers=bob)
    ).status_code == 404
    about_ada_job = await client.post(BASE, headers=bob, json={"job_id": ada_job})
    assert about_ada_job.status_code == 404
    assert len(fake_llm.calls) == calls  # Bob's attempts never reached the model
    assert (
        await client.get(BASE, headers=bob)
    ).json() == []  # nor does his list show Ada's


async def test_list_conversations_newest_first_titled_by_the_first_message(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    older = await _conversation(client, fake_llm, ada)
    fake_llm.queue_stream(PROMPT_VERSION, ["ok"])
    await client.post(
        f"{BASE}/{older}/messages", headers=ada, json={"content": "x" * 200}
    )
    newer = (await client.post(BASE, headers=ada, json={})).json()["id"]
    empty = (await client.get(BASE, headers=ada)).json()
    assert {r["id"]: r["title"] for r in empty}[newer] is None
    fake_llm.queue_stream(PROMPT_VERSION, ["ok"])
    await client.post(f"{BASE}/{newer}/messages", headers=ada, json={"content": "hi"})

    rows = (await client.get(BASE, headers=ada)).json()

    assert [r["id"] for r in rows] == [newer, older]
    assert rows[0]["title"] == "hi"
    assert rows[1]["title"] == "x" * 80


async def test_conversation_needs_a_profile_and_messages_need_app_check(
    app: FastAPI, client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    assert (
        await client.post(BASE, headers=ada, json={})
    ).status_code == 422  # no profile yet

    app.dependency_overrides.pop(verify_app_check)
    zero = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        f"{BASE}/{zero}/messages", headers=ada, json={"content": "hi"}
    )
    assert resp.status_code == 401


async def test_the_turn_is_committed_when_each_request_has_its_own_session(
    real_client: httpx.AsyncClient, fake_llm: FakeLLMGateway, users
):
    """The shared test session hides the real lifecycle: in production the request's DB
    session comes from a ``yield`` dependency, and the turn is stored while (and after) the
    response streams. This runs on committed, per-request sessions."""
    ada = users["ada"]
    conv_id = await _conversation(real_client, fake_llm, ada)
    fake_llm.queue_stream(PROMPT_VERSION, ["Bon", "jour"])

    resp = await real_client.post(
        f"{BASE}/{conv_id}/messages", headers=ada, json={"content": "Salut"}
    )

    assert [n for n, _ in parse_sse(resp.text)] == ["token", "token", "done"]
    stored = (await real_client.get(f"{BASE}/{conv_id}/messages", headers=ada)).json()
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", "Salut"),
        ("assistant", "Bonjour"),
    ]
