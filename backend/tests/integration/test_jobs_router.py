"""/api/v1/jobs through real HTTP (P2-09): the three entry paths + cross-tenant."""

import httpx
import pytest
from fastapi import FastAPI

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.jobs import PROMPT_VERSION
from recruitai.core.app_check import verify_app_check
from recruitai.core.errors import UpstreamUnavailable
from tests.fixtures.jobs import FakeJobProvider
from tests.unit.test_jobs_parser import blank_job

PDF = b"%PDF-1.4\n%jd"


@pytest.fixture
def ada(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}


@pytest.fixture
def bob(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-bob', 'bob@example.com')}"}


async def _upload_jd(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/api/v1/documents",
        headers=headers,
        data={"kind": "jd"},
        files={"file": ("jd.pdf", PDF, "application/pdf")},
    )
    return resp.json()["document_id"]


async def test_three_entry_paths_then_list_and_read(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    fake_llm.queue(PROMPT_VERSION, blank_job())
    manual = await client.post(
        "/api/v1/jobs",
        headers=ada,
        json={"source": "manual", "text": "Dev Python à Lyon"},
    )
    assert manual.status_code == 201
    assert manual.json()["source"] == "manual" and manual.json()["external_id"] is None

    fake_llm.queue(PROMPT_VERSION, blank_job())
    doc = await _upload_jd(client, ada)
    file_job = await client.post(
        "/api/v1/jobs", headers=ada, json={"source": "file", "document_id": doc}
    )
    assert file_job.status_code == 201 and file_job.json()["source"] == "file"

    saved = await client.post(
        "/api/v1/jobs",
        headers=ada,
        json={"source": "france_travail", "external_id": "AB1"},
    )
    again = await client.post(
        "/api/v1/jobs",
        headers=ada,
        json={"source": "france_travail", "external_id": "AB1"},
    )
    assert saved.status_code == 201 and saved.json()["id"] == again.json()["id"]
    assert len(fake_llm.calls) == 2  # saving a provider result costs no LLM call

    listed = (await client.get("/api/v1/jobs", headers=ada)).json()
    assert len(listed) == 3
    page = (await client.get("/api/v1/jobs?limit=2&offset=2", headers=ada)).json()
    assert [j["id"] for j in page] == [listed[2]["id"]]  # newest first, then paged
    assert (await client.get("/api/v1/jobs?limit=0", headers=ada)).status_code == 422
    one = await client.get(f"/api/v1/jobs/{manual.json()['id']}", headers=ada)
    assert one.json() == manual.json()

    # inputs the schema forbids: a URL source (D5), empty text, an unknown offer
    for bad in (
        {"source": "url", "url": "https://x.test/job"},
        {"source": "manual", "text": ""},
    ):
        assert (
            await client.post("/api/v1/jobs", headers=ada, json=bad)
        ).status_code == 422
    missing = await client.post(
        "/api/v1/jobs",
        headers=ada,
        json={"source": "france_travail", "external_id": "MISSING"},
    )
    assert missing.status_code == 404


async def test_search_is_validated_and_cached(
    client: httpx.AsyncClient, fake_job_provider: FakeJobProvider, ada
):
    url = "/api/v1/jobs/search"
    first = await client.get(
        url, headers=ada, params={"query": "python", "department": "Paris"}
    )
    await client.get(
        url, headers=ada, params={"query": "python", "department": "Paris"}
    )
    assert first.status_code == 200 and first.json()["results"][0]["id"] == "AB1"
    assert fake_job_provider.searches == 1
    assert (
        await client.get(url, headers=ada, params={"limit": 500})
    ).status_code == 422
    assert (await client.get(url)).status_code == 401


async def test_org_b_cannot_read_list_or_reference_org_as_jobs(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    fake_llm.queue(PROMPT_VERSION, blank_job())
    job_id = (
        await client.post(
            "/api/v1/jobs", headers=ada, json={"source": "manual", "text": "Dev Python"}
        )
    ).json()["id"]
    ada_doc = await _upload_jd(client, ada)

    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=bob)).status_code == 404
    assert (await client.get("/api/v1/jobs", headers=bob)).json() == []
    stolen = await client.post(
        "/api/v1/jobs", headers=bob, json={"source": "file", "document_id": ada_doc}
    )
    assert stolen.status_code == 404
    assert len(fake_llm.calls) == 1  # Bob's attempt never reached the model


async def test_adding_a_job_requires_app_check_when_enforced(
    app: FastAPI, client: httpx.AsyncClient, ada
):
    app.dependency_overrides.pop(verify_app_check)
    resp = await client.post(
        "/api/v1/jobs", headers=ada, json={"source": "manual", "text": "x"}
    )
    assert resp.status_code == 401


async def test_provider_failure_is_a_503_problem(
    app: FastAPI, client: httpx.AsyncClient, fake_job_provider: FakeJobProvider, ada
):
    async def boom(**_: object) -> None:
        raise UpstreamUnavailable(
            "secret upstream detail", code="job_provider_unavailable"
        )

    fake_job_provider.search = boom  # type: ignore[method-assign,assignment]
    resp = await client.get("/api/v1/jobs/search", headers=ada, params={"query": "x"})
    assert resp.status_code == 503
    assert resp.json()["code"] == "job_provider_unavailable"
