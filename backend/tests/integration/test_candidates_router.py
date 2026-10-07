"""/api/v1/profile through real HTTP (P2-04): walkthrough Flow B + cross-tenant."""

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
