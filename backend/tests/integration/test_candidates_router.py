"""/api/v1/profile through real HTTP: walkthrough Flow B + cross-tenant."""

import httpx
import pytest
from fastapi import FastAPI

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.cv_extract import PROMPT_VERSION
from recruitai.core.app_check import verify_app_check
from recruitai.modules.candidates.schemas import CVInformation, PersonalInfo, RawSkill

PDF = b"%PDF-1.4\n%cv"


def _cv(name: str = "Ada Lovelace") -> CVInformation:
    return CVInformation(
        personal_info=PersonalInfo(name=name, phone="0102030405"),
        formations=[],
        experiences=[],
        skills=[RawSkill(name="Python")],
    )


async def _upload_cv(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/api/v1/documents",
        headers=headers,
        data={"kind": "cv"},
        files={"file": ("cv.pdf", PDF, "application/pdf")},
    )
    return resp.json()["document_id"]


@pytest.fixture
def ada(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}


@pytest.fixture
def bob(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-bob', 'bob@example.com')}"}


async def test_upload_extract_read_and_edit_the_profile(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    assert (await client.get("/api/v1/profile", headers=ada)).status_code == 404

    fake_llm.queue(PROMPT_VERSION, _cv())
    document_id = await _upload_cv(client, ada)
    extracted = await client.post(
        "/api/v1/profile/extract", headers=ada, json={"document_id": document_id}
    )
    assert extracted.status_code == 200
    body = extracted.json()
    assert body["document_id"] == document_id
    assert body["data"]["personal_info"]["name"] == "Ada Lovelace"

    assert (await client.get("/api/v1/profile", headers=ada)).json() == body

    patched = await client.patch(
        "/api/v1/profile", headers=ada, json={"summary": "Mathematician"}
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["summary"] == "Mathematician"
    assert patched.json()["data"]["skills"] == body["data"]["skills"]

    invalid = await client.patch(
        "/api/v1/profile",
        headers=ada,
        json={"personal_info": {"email": "ada@example.com"}},  # name is required
    )
    assert invalid.status_code == 422
    nulled = await client.patch("/api/v1/profile", headers=ada, json={"skills": None})
    assert nulled.status_code == 422  # not a 500: a required section can't be erased


async def test_org_b_cannot_read_edit_or_extract_org_as_profile(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    fake_llm.queue(PROMPT_VERSION, _cv())
    ada_doc = await _upload_cv(client, ada)
    await client.post(
        "/api/v1/profile/extract", headers=ada, json={"document_id": ada_doc}
    )

    assert (await client.get("/api/v1/profile", headers=bob)).status_code == 404
    assert (
        await client.patch("/api/v1/profile", headers=bob, json={"summary": "x"})
    ).status_code == 404
    stolen = await client.post(
        "/api/v1/profile/extract", headers=bob, json={"document_id": ada_doc}
    )
    assert stolen.status_code == 404
    assert len(fake_llm.calls) == 1  # Bob's attempt never reached the model


async def test_extract_requires_app_check_when_enforced(
    app: FastAPI, client: httpx.AsyncClient, ada
):
    app.dependency_overrides.pop(verify_app_check)
    resp = await client.post(
        "/api/v1/profile/extract",
        headers=ada,
        json={"document_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 401


async def test_memory_round_trip_limits_and_tenant_isolation(
    client: httpx.AsyncClient, ada, bob
):
    assert (await client.get("/api/v1/profile/memory", headers=ada)).json() == {
        "facts": []
    }  # no CV needed
    put = await client.put(
        "/api/v1/profile/memory",
        headers=ada,
        # NUL (JSONB refuses it) and hidden characters are stripped, never a 500
        json={
            "facts": [
                {"text": "  Prefers\x00 remote\u200b work\u202e "},
                {"text": "Speaks French"},
            ]
        },
    )
    assert put.status_code == 200
    facts = put.json()["facts"]
    assert [f["text"] for f in facts] == ["Prefers remote work", "Speaks French"]
    kept = await client.put(
        "/api/v1/profile/memory", headers=ada, json={"facts": facts[1:]}
    )
    assert kept.json()["facts"] == facts[1:]  # id and date survive a replace
    assert (await client.get("/api/v1/profile/memory", headers=ada)).json() == {
        "facts": facts[1:]
    }

    for bad in ([{"text": "x"}] * 31, [{"text": "x" * 201}], [{"text": "  "}]):
        resp = await client.put(
            "/api/v1/profile/memory", headers=ada, json={"facts": bad}
        )
        assert resp.status_code == 422
        assert resp.headers["content-type"] == "application/problem+json"

    assert (await client.get("/api/v1/profile/memory", headers=bob)).json() == {
        "facts": []
    }
    await client.put("/api/v1/profile/memory", headers=bob, json={"facts": []})
    assert (await client.get("/api/v1/profile/memory", headers=ada)).json() == {
        "facts": facts[1:]
    }


async def test_remember_tool_and_memory_reader(db_session):
    from recruitai.core import tools as registry
    from recruitai.modules.candidates import service as candidates
    from recruitai.modules.candidates import tools as _registers  # noqa: F401
    from recruitai.modules.candidates.schemas import FactIn
    from recruitai.modules.candidates.service import MemoryFull
    from recruitai.modules.identity.models import Organization

    org = Organization(name="mem", kind="personal")
    db_session.add(org)
    await db_session.flush()

    def call(text: str = "") -> registry.Call:
        return registry.Call(db_session, None, org.id, None, None, {"text": text})

    async def said(text: str) -> dict[str, str]:
        return await registry.handler("remember")(call(text))

    assert await registry.read("memory", call()) is None
    # Settings (PUT) and the chat get the same raw text: one rule, one stored fact
    raw = " Wants a\u200b  Paris\x00 job\u202e "
    await candidates.put_memory(db_session, org_id=org.id, facts=[FactIn(text=raw)])
    assert await said(raw) == {"status": "already saved"}
    assert await said("Wants a Paris job") == {"status": "already saved"}
    for i in range(29):
        await said(f"fact {i}")
    with pytest.raises(MemoryFull):
        await said("one too many")
    memory = await registry.read("memory", call())
    assert memory is not None
    assert memory["text"].startswith("- Wants a Paris job\n- fact 0")
    assert memory["text"].count("\n") == 29
