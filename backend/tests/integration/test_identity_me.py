"""GET /api/v1/me (P1-08): the auth+tenancy pipeline end to end, walkthrough §3 Flow A."""

import httpx


async def test_first_visit_provisions_and_returns_onboarding(
    client: httpx.AsyncClient, emulator_token
):
    token = emulator_token("uid-me-1", "me1@example.test")

    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "me1@example.test"
    assert body["onboarding"] == {"has_profile": False}
    assert body["active_org_id"]  # a real org id, freshly provisioned


async def test_returning_user_gets_the_same_active_org(
    client: httpx.AsyncClient, emulator_token
):
    token = emulator_token("uid-me-2", "me2@example.test")
    first = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    second = await client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert first.json()["active_org_id"] == second.json()["active_org_id"]


async def test_missing_auth_is_401_problem_json(client: httpx.AsyncClient):
    resp = await client.get("/api/v1/me")

    assert resp.status_code == 401
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json()["code"] == "unauthorized"


async def test_onboarding_has_profile_turns_true_once_a_profile_exists(
    client, fake_llm, emulator_token
):
    from tests.integration.test_matching_router import _add_profile

    headers = {
        "Authorization": f"Bearer {emulator_token('uid-onb', 'onb@example.com')}"
    }
    before = (await client.get("/api/v1/me", headers=headers)).json()
    assert before["onboarding"] == {"has_profile": False}

    await _add_profile(client, fake_llm, headers)

    after = (await client.get("/api/v1/me", headers=headers)).json()
    assert after["onboarding"] == {"has_profile": True}
