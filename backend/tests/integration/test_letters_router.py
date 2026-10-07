"""/api/v1/letters through real HTTP (P2-18): the editing flow + cross-tenant."""

import httpx
import pytest
from fastapi import FastAPI

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.letters import PROMPT_VERSION
from recruitai.core.app_check import verify_app_check
from recruitai.modules.letters.schemas import BlockText
from tests.integration.test_letters_service import DRAFT
from tests.integration.test_matching_router import _add_job, _add_profile


@pytest.fixture
def ada(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}


@pytest.fixture
def bob(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-bob', 'bob@example.com')}"}


async def _letter(
    client: httpx.AsyncClient, llm: FakeLLMGateway, who
) -> tuple[str, str]:
    await _add_profile(client, llm, who)
    job_id = await _add_job(client, llm, who)
    llm.queue(PROMPT_VERSION, DRAFT)
    resp = await client.post(
        "/api/v1/letters",
        headers=who,
        json={"job_id": job_id, "tone": "warm", "language": "fr", "template": "modern"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], job_id


async def test_create_edit_regenerate_versions_and_restore(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    letter_id, job_id = await _letter(client, fake_llm, ada)
    got = (await client.get(f"/api/v1/letters/{letter_id}", headers=ada)).json()
    assert (got["tone"], got["template"], got["status"], got["render_status"]) == (
        "warm", "modern", "draft", "none",
    )  # fmt: skip
    assert got["content"]["subject"] == DRAFT.subject
    assert got["content"]["header"]["name"] == "Ada"  # from the profile, not the model

    patched = await client.patch(
        f"/api/v1/letters/{letter_id}/blocks/subject",
        headers=ada,
        json={"text": "Mon objet"},
    )
    assert patched.json()["content"]["subject"] == "Mon objet"

    fake_llm.queue(PROMPT_VERSION, BlockText(text="Paragraphe réécrit."))
    regenerated = await client.post(
        f"/api/v1/letters/{letter_id}/blocks/body/regenerate",
        headers=ada,
        json={"index": 0},
    )
    body = regenerated.json()["content"]["body"]
    assert body[0] == "Paragraphe réécrit." and body[1:] == DRAFT.body[1:]

    versions = (
        await client.get(f"/api/v1/letters/{letter_id}/versions", headers=ada)
    ).json()
    assert [v["n"] for v in versions] == [3, 2, 1]
    restored = await client.post(
        f"/api/v1/letters/{letter_id}/versions/1/restore", headers=ada
    )
    assert restored.json()["content"]["subject"] == DRAFT.subject
    assert (
        await client.post(
            f"/api/v1/letters/{letter_id}/versions/99/restore", headers=ada
        )
    ).status_code == 404

    listed = await client.get(f"/api/v1/letters?job_id={job_id}", headers=ada)
    assert [x["id"] for x in listed.json()] == [letter_id]


async def test_bad_input_is_a_clean_4xx_and_costs_no_model_call(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    letter_id, job_id = await _letter(client, fake_llm, ada)
    calls = len(fake_llm.calls)
    url = f"/api/v1/letters/{letter_id}/blocks"

    assert (
        await client.patch(f"{url}/body", headers=ada, json={"text": "x"})
    ).status_code == 422
    assert (
        await client.patch(f"{url}/subject", headers=ada, json={"text": " "})
    ).status_code == 422
    assert (
        await client.patch(f"{url}/nope", headers=ada, json={"text": "x"})
    ).status_code == 422
    assert (await client.post(f"{url}/body/regenerate", headers=ada)).status_code == 422
    bad_tone = await client.post(
        "/api/v1/letters", headers=ada, json={"job_id": job_id, "tone": "rude"}
    )
    assert bad_tone.status_code == 422
    no_job = await client.post(
        "/api/v1/letters",
        headers=ada,
        json={"job_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert no_job.status_code == 404
    assert len(fake_llm.calls) == calls


async def test_letter_without_a_profile_is_a_422(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada
):
    job_id = await _add_job(client, fake_llm, ada)
    resp = await client.post("/api/v1/letters", headers=ada, json={"job_id": job_id})
    assert resp.status_code == 422


async def test_org_b_cannot_read_edit_regenerate_or_restore_org_as_letter(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    letter_id, job_id = await _letter(client, fake_llm, ada)
    await _add_profile(client, fake_llm, bob)
    calls = len(fake_llm.calls)
    base = f"/api/v1/letters/{letter_id}"

    assert (await client.get(base, headers=bob)).status_code == 404
    edit = await client.patch(
        f"{base}/blocks/subject", headers=bob, json={"text": "hacked"}
    )
    assert edit.status_code == 404
    regen = await client.post(f"{base}/blocks/subject/regenerate", headers=bob)
    assert regen.status_code == 404
    assert (await client.get(f"{base}/versions", headers=bob)).status_code == 404
    assert (
        await client.post(f"{base}/versions/1/restore", headers=bob)
    ).status_code == 404
    stolen = await client.post("/api/v1/letters", headers=bob, json={"job_id": job_id})
    assert stolen.status_code == 404
    assert (await client.get("/api/v1/letters", headers=bob)).json() == []
    assert len(fake_llm.calls) == calls  # none of it reached the model
    untouched = (await client.get(base, headers=ada)).json()
    assert untouched["content"]["subject"] == DRAFT.subject


async def test_generating_and_regenerating_require_app_check_when_enforced(
    app: FastAPI, client: httpx.AsyncClient, ada
):
    app.dependency_overrides.pop(verify_app_check)
    zero = "00000000-0000-0000-0000-000000000000"
    create = await client.post("/api/v1/letters", headers=ada, json={"job_id": zero})
    regen = await client.post(
        f"/api/v1/letters/{zero}/blocks/subject/regenerate", headers=ada
    )
    assert (create.status_code, regen.status_code) == (401, 401)


async def test_export_as_text_and_email_and_cross_tenant(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    letter_id, _ = await _letter(client, fake_llm, ada)
    base = f"/api/v1/letters/{letter_id}/export"

    text = (await client.get(f"{base}?format=text", headers=ada)).json()
    assert text["format"] == "text" and text["subject"] is None
    assert text["body"].startswith(DRAFT.salutation) and "Ada" in text["body"]
    email = (await client.get(f"{base}?format=email", headers=ada)).json()
    assert email["subject"] == DRAFT.subject and DRAFT.closing in email["body"]

    assert (
        await client.get(f"{base}?format=docx", headers=ada)
    ).status_code == 422  # v2
    assert (
        await client.get(base, headers=ada)
    ).status_code == 422  # format is required
    assert (await client.get(f"{base}?format=text", headers=bob)).status_code == 404


async def test_check_flags_an_edited_in_invention_and_is_org_scoped(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    letter_id, _ = await _letter(client, fake_llm, ada)
    base = f"/api/v1/letters/{letter_id}"

    clean = (await client.get(f"{base}/check", headers=ada)).json()
    assert [
        c["term"] for c in clean["unsupported_claims"] if c["kind"] == "skill"
    ] == []
    assert clean["quality"]["target_words"] == 250  # the default length

    await client.patch(
        f"{base}/blocks/opening",
        headers=ada,
        json={"text": "J'ai dirigé la migration Kubernetes chez Google en 2019."},
    )
    flagged = (await client.get(f"{base}/check", headers=ada)).json()
    terms = {(c["kind"], c["term"]) for c in flagged["unsupported_claims"]}
    assert {("skill", "Kubernetes"), ("name", "Google")} <= terms

    assert (await client.get(f"{base}/check", headers=bob)).status_code == 404


async def test_assist_endpoint_contract_cross_tenant_and_app_check(
    app: FastAPI, client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    letter_id, _ = await _letter(client, fake_llm, ada)
    url = f"/api/v1/letters/{letter_id}/assist"
    fake_llm.queue("letter_assist@1", BlockText(text="Plus court."))

    ok = await client.post(
        url,
        headers=ada,
        json={
            "block": "opening",
            "selection": "Je vous écris pour",
            "action": "shorten",
        },
    )
    assert ok.status_code == 200 and ok.json() == {"suggestion": "Plus court."}
    unchanged = (await client.get(f"/api/v1/letters/{letter_id}", headers=ada)).json()
    assert (
        unchanged["content"]["opening"] == DRAFT.opening
    )  # the endpoint saved nothing

    bad = {"block": "opening", "selection": "x", "action": "translate"}
    assert (await client.post(url, headers=ada, json=bad)).status_code == 422
    outside = {"block": "closing", "selection": "Je vous écris", "action": "shorten"}
    assert (await client.post(url, headers=ada, json=outside)).status_code == 422
    calls = len(fake_llm.calls)
    stolen = await client.post(url, headers=bob, json={**outside, "block": "opening"})
    assert stolen.status_code == 404 and len(fake_llm.calls) == calls

    app.dependency_overrides.pop(verify_app_check)
    no_app_check = await client.post(
        url,
        headers=ada,
        json={"block": "opening", "selection": "x", "action": "shorten"},
    )
    assert no_app_check.status_code == 401


async def test_delete_removes_the_letter_and_only_for_its_owner(
    client: httpx.AsyncClient, fake_llm: FakeLLMGateway, ada, bob
):
    letter_id, _ = await _letter(client, fake_llm, ada)
    url = f"/api/v1/letters/{letter_id}"

    assert (await client.delete(url, headers=bob)).status_code == 404  # not bob's
    assert (await client.get(url, headers=ada)).status_code == 200  # still there

    assert (await client.delete(url, headers=ada)).status_code == 204
    assert (await client.get(url, headers=ada)).status_code == 404
    assert (await client.delete(url, headers=ada)).status_code == 404
