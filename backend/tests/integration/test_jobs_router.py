"""/api/v1/jobs through real HTTP (P2-09): the three entry paths + cross-tenant."""

import httpx
import pytest
from fastapi import FastAPI

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.jobs import (
    INDEX_PROMPT_VERSION,
    JOB_QUERY_VERSION,
    ONE_PROMPT_VERSION,
    PROMPT_VERSION,
)
from recruitai.core.app_check import verify_app_check
from recruitai.core.errors import UpstreamUnavailable
from recruitai.modules.jobs.schemas import OfferIndex, ParsedQuery
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

    fake_llm.queue(INDEX_PROMPT_VERSION, OfferIndex(offers=["A", "B"]))
    fake_llm.queue(ONE_PROMPT_VERSION, blank_job())
    fake_llm.queue(ONE_PROMPT_VERSION, blank_job())
    doc = await _upload_jd(client, ada)
    file_jobs = await client.post(
        "/api/v1/jobs/from-file",
        headers=ada,
        json={"source": "file", "document_ids": [doc]},
    )
    assert file_jobs.status_code == 201
    assert [j["source"] for j in file_jobs.json()] == ["file", "file"]

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
    assert (
        len(fake_llm.calls) == 4
    )  # manual + index + 2 offers; a provider result costs none

    listed = (await client.get("/api/v1/jobs", headers=ada)).json()
    assert len(listed) == 4  # manual + two from the file + the saved search result
    page = (await client.get("/api/v1/jobs?limit=2&offset=2", headers=ada)).json()
    assert [j["id"] for j in page] == [
        listed[2]["id"],
        listed[3]["id"],
    ]  # newest first, then paged
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


async def test_repeats_return_the_existing_job_and_a_job_can_be_deleted(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    body = {"source": "manual", "text": "Dev Python à Lyon"}
    fake_llm.queue(PROMPT_VERSION, blank_job())
    first = await client.post("/api/v1/jobs", headers=ada, json=body)
    repeat = await client.post("/api/v1/jobs", headers=ada, json=body)
    assert (first.status_code, repeat.status_code) == (201, 200)
    assert repeat.json()["id"] == first.json()["id"]

    fake_llm.queue(INDEX_PROMPT_VERSION, OfferIndex(offers=["A"]))
    fake_llm.queue(ONE_PROMPT_VERSION, blank_job())
    doc = await _upload_jd(client, ada)
    same_bytes = await _upload_jd(client, ada)  # a second document, identical content
    created = await client.post(
        "/api/v1/jobs/from-file",
        headers=ada,
        json={"source": "file", "document_ids": [doc]},
    )
    repeated = await client.post(
        "/api/v1/jobs/from-file",
        headers=ada,
        json={"source": "file", "document_ids": [same_bytes]},
    )
    assert (created.status_code, repeated.status_code) == (201, 200)
    assert repeated.json() == created.json()
    assert (
        len(fake_llm.calls) == 3
    )  # text + index + one offer; the repeats cost nothing

    job_id = first.json()["id"]
    assert (
        await client.delete(f"/api/v1/jobs/{job_id}", headers=bob)
    ).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=ada)).status_code == 200
    assert (
        await client.delete(f"/api/v1/jobs/{job_id}", headers=ada)
    ).status_code == 204
    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=ada)).status_code == 404
    assert (
        await client.delete(f"/api/v1/jobs/{job_id}", headers=ada)
    ).status_code == 404

    fake_llm.queue(PROMPT_VERSION, blank_job())  # deleted: pasting it again starts over
    again = await client.post("/api/v1/jobs", headers=ada, json=body)
    assert again.status_code == 201 and again.json()["id"] != job_id


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
        "/api/v1/jobs/from-file",
        headers=bob,
        json={"source": "file", "document_ids": [ada_doc]},
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


async def test_a_sentence_becomes_filters_and_unusable_parts_are_said_not_guessed(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    fake_llm.queue(
        JOB_QUERY_VERSION,
        ParsedQuery(
            keywords="data analyst",
            places=["Lyon", "69"],
            contract_types=["cdi", "not a code!"],
            remote=True,
            notes=["salary above 45k"],
        ),
    )

    r = await client.post(
        "/api/v1/jobs/query",
        headers=ada,
        json={"text": "remote data analyst jobs in Lyon, CDI, more than 45k"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["query"], body["remote"]) == ("data analyst", True)
    assert body["department"] == "69"  # canonical code, deduplicated
    assert body["contract_type"] is None  # one bad code drops the field...
    assert any("Contract not recognised" in n for n in body["notes"])  # ...and says so
    assert "salary above 45k" in body["notes"]


async def test_manual_company_address_and_location_flow_into_letter_and_application(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    fake_llm.queue(PROMPT_VERSION, blank_job())
    job_id = (
        await client.post(
            "/api/v1/jobs", headers=ada, json={"source": "manual", "text": "Dev Python"}
        )
    ).json()["id"]
    url = f"/api/v1/jobs/{job_id}"
    assert (
        await client.patch(url, headers=bob, json={"company_name": "x"})
    ).status_code == 404

    body = {
        "company_name": " Acme ",
        "company_address": "1 rue X, Paris",
        "location": "Paris",
    }
    got = (await client.patch(url, headers=ada, json=body)).json()
    assert got["data"]["company"]["name"] == "Acme"
    assert got["data"]["company"]["address"] == "1 rue X, Paris"
    assert got["data"]["badges"]["location"] == "Paris"
    app = (
        await client.post("/api/v1/applications", headers=ada, json={"job_id": job_id})
    ).json()
    assert (app["company_name"], app["location"]) == ("Acme", "Paris")

    cleared = (await client.patch(url, headers=ada, json={"location": "  "})).json()
    assert cleared["data"]["badges"]["location"] is None
    assert cleared["data"]["company"]["name"] == "Acme"  # unsent fields stay
    too_long = await client.patch(url, headers=ada, json={"company_name": "x" * 201})
    assert too_long.status_code == 422
