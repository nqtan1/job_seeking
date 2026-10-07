"""/api/v1/fit-analyses through real HTTP (P2-13): the fit report flow + cross-tenant."""

import httpx
import pytest
from fastapi import FastAPI

from recruitai.ai.gateway import FakeLLMGateway, TextPart
from recruitai.ai.prompts import cv_extract, fit, jobs
from recruitai.core.app_check import verify_app_check
from recruitai.modules.candidates.schemas import CVInformation, PersonalInfo, RawSkill
from recruitai.modules.matching.schemas import FitCheck
from tests.unit.test_jobs_parser import blank_job
from tests.unit.test_schemas import VALID

PDF = b"%PDF-1.4\n%cv"


@pytest.fixture
def ada(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}


@pytest.fixture
def bob(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-bob', 'bob@example.com')}"}


async def _add_job(client: httpx.AsyncClient, llm: FakeLLMGateway, who) -> str:
    llm.queue(jobs.PROMPT_VERSION, blank_job())
    resp = await client.post(
        "/api/v1/jobs", headers=who, json={"source": "manual", "text": "Dev Python"}
    )
    return resp.json()["id"]


async def _add_profile(client: httpx.AsyncClient, llm: FakeLLMGateway, who) -> None:
    upload = await client.post(
        "/api/v1/documents",
        headers=who,
        data={"kind": "cv"},
        files={"file": ("cv.pdf", PDF, "application/pdf")},
    )
    llm.queue(
        cv_extract.PROMPT_VERSION,
        CVInformation(
            personal_info=PersonalInfo(name="Ada"),
            formations=[],
            experiences=[],
            skills=[RawSkill(name="Python")],
        ),
    )
    await client.post(
        "/api/v1/profile/extract",
        headers=who,
        json={"document_id": upload.json()["document_id"]},
    )


async def test_fit_report_is_generated_stored_and_listed(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    await _add_profile(client, fake_llm, ada)
    job_id = await _add_job(client, fake_llm, ada)
    fake_llm.queue(fit.PROMPT_VERSION, FitCheck.model_validate(VALID))
    before = len(fake_llm.calls)

    resp = await client.post(
        "/api/v1/fit-analyses",
        headers=ada,
        json={"job_id": job_id, "company_type": "startup"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert (body["score"], body["verdict"], body["company_type"]) == (
        72,
        "go",
        "startup",
    )
    assert body["job_id"] == job_id and body["model"] == "fake-smart"
    assert body["data"]["strengths"] == ["Python"]
    call = fake_llm.calls[before]
    assert call.model == "smart" and "startup founder" in call.system
    sent = " ".join(p.text for p in call.parts if isinstance(p, TextPart))
    assert "Python" in sent and "<job>" in sent  # profile and job travel as fenced data

    listed = await client.get(f"/api/v1/fit-analyses?job_id={job_id}", headers=ada)
    assert [r["id"] for r in listed.json()] == [body["id"]]
    assert (
        await client.get("/api/v1/fit-analyses?job_id=" + "0" * 32, headers=ada)
    ).json() == []


async def test_missing_profile_unknown_job_and_bad_company_type_are_clean_errors(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    job_id = await _add_job(client, fake_llm, ada)
    before = len(fake_llm.calls)

    no_profile = await client.post(
        "/api/v1/fit-analyses", headers=ada, json={"job_id": job_id}
    )
    assert no_profile.status_code == 422  # a validation problem, not a 404 or 500
    no_job = await client.post(
        "/api/v1/fit-analyses",
        headers=ada,
        json={"job_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert no_job.status_code == 404
    bad_type = await client.post(
        "/api/v1/fit-analyses",
        headers=ada,
        json={"job_id": job_id, "company_type": "ngo"},
    )
    assert bad_type.status_code == 422
    assert len(fake_llm.calls) == before  # none of them reached the model


async def test_org_b_cannot_analyze_or_see_org_as_jobs_and_reports(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    await _add_profile(client, fake_llm, ada)
    ada_job = await _add_job(client, fake_llm, ada)
    fake_llm.queue(fit.PROMPT_VERSION, FitCheck.model_validate(VALID))
    await client.post("/api/v1/fit-analyses", headers=ada, json={"job_id": ada_job})
    await _add_profile(client, fake_llm, bob)
    before = len(fake_llm.calls)

    stolen = await client.post(
        "/api/v1/fit-analyses", headers=bob, json={"job_id": ada_job}
    )
    assert stolen.status_code == 404
    assert len(fake_llm.calls) == before
    assert (await client.get("/api/v1/fit-analyses", headers=bob)).json() == []
    by_job = await client.get(f"/api/v1/fit-analyses?job_id={ada_job}", headers=bob)
    assert by_job.json() == []


async def test_fit_analysis_requires_app_check_when_enforced(
    app: FastAPI, client: httpx.AsyncClient, ada
):
    app.dependency_overrides.pop(verify_app_check)
    resp = await client.post(
        "/api/v1/fit-analyses",
        headers=ada,
        json={"job_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 401
