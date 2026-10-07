"""/api/v1/applications through real HTTP (P2-27) + cross-tenant (P2-27) + edges (P2-28)."""

import httpx
import pytest

from recruitai.ai.gateway import FakeLLMGateway
from tests.integration.test_matching_router import _add_job, _add_profile

BASE = "/api/v1/applications"


@pytest.fixture
def ada(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}


@pytest.fixture
def bob(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-bob', 'bob@example.com')}"}


async def test_an_empty_tracker_is_an_empty_list_not_an_error(
    client: httpx.AsyncClient, ada
):
    assert (await client.get(BASE, headers=ada)).json() == []
    assert (await client.get(f"{BASE}?status=offer", headers=ada)).json() == []


async def test_track_an_application_from_to_apply_to_offer_with_its_timeline(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    await _add_profile(client, fake_llm, ada)
    job_id = await _add_job(client, fake_llm, ada)

    created = await client.post(
        BASE,
        headers=ada,
        json={"job_id": job_id, "source": "france_travail", "notes": "via FT"},
    )
    assert created.status_code == 201
    app = created.json()
    assert (app["company_name"], app["status"], app["job_id"]) == (
        "Acme",
        "to_apply",
        job_id,
    )
    assert app["next_statuses"] == ["applied"] and app["applied_at"] is None
    url = f"{BASE}/{app['id']}"

    applied = await client.post(
        f"{url}/status", headers=ada, json={"status": "applied", "note": "sent"}
    )
    assert applied.status_code == 200 and applied.json()["applied_at"] is not None
    assert "interview" in applied.json()["next_statuses"]
    await client.post(f"{url}/status", headers=ada, json={"status": "interview"})
    offer = await client.post(f"{url}/status", headers=ada, json={"status": "offer"})
    assert offer.json()["status"] == "offer" and offer.json()["next_statuses"] == [
        "rejected"
    ]

    timeline = (await client.get(f"{url}/events", headers=ada)).json()
    assert [(e["from_status"], e["to_status"]) for e in timeline] == [
        (None, "to_apply"), ("to_apply", "applied"), ("applied", "interview"), ("interview", "offer"),
    ]  # fmt: skip
    assert timeline[1]["note"] == "sent"

    patched = await client.patch(
        url, headers=ada, json={"notes": None, "job_title": "Dev"}
    )
    assert patched.json()["notes"] is None and patched.json()["job_title"] == "Dev"
    assert patched.json()["status"] == "offer"  # PATCH never touches the status

    by_status = await client.get(f"{BASE}?status=offer", headers=ada)
    assert [a["id"] for a in by_status.json()] == [app["id"]]
    assert (await client.get(f"{BASE}?status=to_apply", headers=ada)).json() == []

    assert (await client.delete(url, headers=ada)).status_code == 204
    assert (await client.get(url, headers=ada)).status_code == 404
    assert (await client.get(f"{url}/events", headers=ada)).status_code == 404


async def test_bad_input_and_illegal_moves_are_clean_4xx_with_the_allowed_options(
    client: httpx.AsyncClient, ada
):
    for bad in (
        {},  # no company and no job
        {"company_name": "Acme", "source": "tiktok"},
        {"company_name": "Acme", "status": "offer"},
        {"company_name": "Acme", "notes": "x" * 5001},
    ):
        assert (await client.post(BASE, headers=ada, json=bad)).status_code == 422
    unknown_job = {"job_id": "00000000-0000-0000-0000-000000000000"}
    assert (await client.post(BASE, headers=ada, json=unknown_job)).status_code == 404

    app = (await client.post(BASE, headers=ada, json={"company_name": "Acme"})).json()
    url = f"{BASE}/{app['id']}"
    illegal = await client.post(f"{url}/status", headers=ada, json={"status": "offer"})
    assert illegal.status_code == 422
    assert (
        "to_apply" in illegal.json()["detail"] and "applied" in illegal.json()["detail"]
    )
    assert (
        await client.post(f"{url}/status", headers=ada, json={"status": "hired"})
    ).status_code == 422
    assert (
        await client.patch(url, headers=ada, json={"company_name": None})
    ).status_code == 422
    assert (await client.patch(url, headers=ada, json={"status": "offer"})).json()[
        "status"
    ] == "to_apply"
    await client.post(f"{url}/status", headers=ada, json={"status": "applied"})
    await client.post(f"{url}/status", headers=ada, json={"status": "rejected"})
    final = await client.post(f"{url}/status", headers=ada, json={"status": "applied"})
    assert final.status_code == 422 and "final" in final.json()["detail"]
    same = await client.post(f"{url}/status", headers=ada, json={"status": "rejected"})
    assert same.status_code == 422  # staying put is not a move
    timeline = (await client.get(f"{url}/events", headers=ada)).json()
    assert len(timeline) == 3  # creation + 2 legal moves; refused moves left no trace


async def test_org_b_cannot_read_change_or_delete_org_as_applications(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    await _add_profile(client, fake_llm, ada)
    job_id = await _add_job(client, fake_llm, ada)
    app = (await client.post(BASE, headers=ada, json={"job_id": job_id})).json()
    url = f"{BASE}/{app['id']}"

    assert (await client.get(url, headers=bob)).status_code == 404
    assert (
        await client.patch(url, headers=bob, json={"notes": "x"})
    ).status_code == 404
    assert (
        await client.post(f"{url}/status", headers=bob, json={"status": "applied"})
    ).status_code == 404
    assert (await client.get(f"{url}/events", headers=bob)).status_code == 404
    assert (await client.delete(url, headers=bob)).status_code == 404
    assert (
        await client.post(BASE, headers=bob, json={"job_id": job_id})
    ).status_code == 404
    assert (await client.get(BASE, headers=bob)).json() == []

    untouched = (await client.get(url, headers=ada)).json()
    assert untouched["status"] == "to_apply" and untouched["notes"] is None
    assert len((await client.get(f"{url}/events", headers=ada)).json()) == 1


async def test_attach_list_and_detach_documents_with_tenant_isolation(
    client: httpx.AsyncClient, ada, bob
):
    app = (
        await client.post(
            BASE, headers=ada, json={"company_name": "Acme", "source": "other"}
        )
    ).json()
    cv = (
        await client.post(
            "/api/v1/documents",
            headers=ada,
            data={"kind": "cv"},
            files={"file": ("cv.txt", b"Ada Lovelace, engineer", "text/plain")},
        )
    ).json()["document_id"]
    docs = f"{BASE}/{app['id']}/documents"

    assert (
        await client.post(docs, headers=ada, json={"document_id": cv})
    ).status_code == 204
    # attaching twice is a no-op
    assert (
        await client.post(docs, headers=ada, json={"document_id": cv})
    ).status_code == 204
    listed = (await client.get(docs, headers=ada)).json()
    assert [d["document_id"] for d in listed] == [cv] and listed[0]["download_url"]
    assert listed[0]["filename"] == "CV.txt"  # no profile yet: no name to add
    assert "dl=1" in listed[0]["save_url"] and "dl=0" in listed[0]["download_url"]

    # another tenant sees neither the application nor the file
    assert (await client.get(docs, headers=bob)).status_code == 404
    other = (
        await client.post(
            BASE, headers=bob, json={"company_name": "Evil", "source": "other"}
        )
    ).json()
    stolen = await client.post(
        f"{BASE}/{other['id']}/documents", headers=bob, json={"document_id": cv}
    )
    assert stolen.status_code == 404

    assert (await client.delete(f"{docs}/{cv}", headers=ada)).status_code == 204
    assert (await client.get(docs, headers=ada)).json() == []


async def test_notes_contact_and_interview_date_can_be_edited_later(
    client: httpx.AsyncClient, ada
):
    app = (
        await client.post(
            BASE, headers=ada, json={"company_name": "Acme", "source": "other"}
        )
    ).json()
    assert app["contact"] is None and app["interview_at"] is None

    edited = await client.patch(
        f"{BASE}/{app['id']}",
        headers=ada,
        json={
            "notes": "Call went well",
            "contact": "Marie Curie, marie@acme.test",
            "interview_at": "2026-10-20T14:00:00+02:00",
        },
    )

    assert edited.status_code == 200
    body = edited.json()
    assert body["notes"] == "Call went well"
    assert body["contact"] == "Marie Curie, marie@acme.test"
    assert body["interview_at"].startswith("2026-10-20T12:00:00")  # stored as UTC
