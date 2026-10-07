"""GET /api/v1/admin/users: only a verified, allowlisted email gets in."""

import uuid

import httpx

from recruitai.config import get_settings
from tests.fixtures.auth import _BASE, _host, mint_emulator_token


def _verified_token(uid: str, email: str) -> str:
    httpx.post(
        f"http://{_host()}/{_BASE}/projects/demo-recruitai/accounts",
        headers={"Authorization": "Bearer owner"},
        json={
            "localId": uid,
            "email": email,
            "password": "test-password-123",
            "emailVerified": True,
        },
        timeout=10,
    ).raise_for_status()
    return mint_emulator_token(uid, email)


async def test_only_an_allowlisted_verified_email_can_list_users(
    client: httpx.AsyncClient, app, emulator_token
):
    tag = uuid.uuid4().hex[:8]
    boss_email, other_email = f"boss-{tag}@example.test", f"nobody-{tag}@example.test"
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"admin_emails": [boss_email]}
    )
    boss = {"Authorization": f"Bearer {_verified_token(f'uid-boss-{tag}', boss_email)}"}
    other = {
        "Authorization": f"Bearer {emulator_token(f'uid-nobody-{tag}', other_email)}"
    }
    await client.get("/api/v1/me", headers=other)  # provisions a user to find

    assert (await client.get("/api/v1/admin/users", headers=other)).status_code == 403
    assert (await client.get("/api/v1/admin/users")).status_code == 401
    ok = await client.get(f"/api/v1/admin/users?q=nobody-{tag}", headers=boss)
    assert ok.status_code == 200
    body = ok.json()
    assert body["total"] == 1 and body["items"][0]["email"] == other_email
    assert "firebase_uid" not in body["items"][0]


async def test_stats_are_aggregates_for_admins_only(
    client: httpx.AsyncClient, app, emulator_token
):
    tag = uuid.uuid4().hex[:8]
    boss_email = f"boss-{tag}@example.test"
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"admin_emails": [boss_email]}
    )
    boss = {"Authorization": f"Bearer {_verified_token(f'uid-boss-{tag}', boss_email)}"}
    other = {
        "Authorization": f"Bearer {emulator_token(f'uid-n-{tag}', f'n-{tag}@example.test')}"
    }

    await client.get("/api/v1/me", headers=other)  # provisions one user to count
    assert (await client.get("/api/v1/admin/stats", headers=other)).status_code == 403
    body = (await client.get("/api/v1/admin/stats", headers=boss)).json()
    assert body["users"]["total"] >= 1 and body["users"]["new_7d"] >= 1
    assert set(body["content"]) == {"profiles", "jobs", "letters", "applications"}
    assert isinstance(body["applications_by_status"], dict)


async def test_block_refuses_every_request_until_unblocked_and_is_audited(
    client: httpx.AsyncClient, app, emulator_token, db_session
):
    from sqlalchemy import select

    from recruitai.modules.identity.models import AdminAction

    tag = uuid.uuid4().hex[:8]
    boss_email = f"boss-{tag}@example.test"
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"admin_emails": [boss_email]}
    )
    boss = {"Authorization": f"Bearer {_verified_token(f'uid-boss-{tag}', boss_email)}"}
    victim_token = emulator_token(f"uid-v-{tag}", f"v-{tag}@example.test")
    victim = {"Authorization": f"Bearer {victim_token}"}
    assert (await client.get("/api/v1/me", headers=victim)).status_code == 200
    listed = (await client.get(f"/api/v1/admin/users?q=v-{tag}", headers=boss)).json()
    victim_id = listed["items"][0]["id"]
    assert listed["items"][0]["blocked"] is False

    assert (
        await client.post(f"/api/v1/admin/users/{victim_id}/block", headers=victim)
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/admin/users/{victim_id}/block", headers=boss)
    ).status_code == 204
    # The token the user already holds stops working at once.
    assert (await client.get("/api/v1/me", headers=victim)).status_code == 403
    assert (await client.get(f"/api/v1/admin/users?q=v-{tag}", headers=boss)).json()[
        "items"
    ][0]["blocked"] is True

    assert (
        await client.post(f"/api/v1/admin/users/{victim_id}/unblock", headers=boss)
    ).status_code == 204
    assert (await client.get("/api/v1/me", headers=victim)).status_code == 200

    actions = (await db_session.execute(select(AdminAction.action))).scalars().all()
    assert actions.count("block") >= 1 and actions.count("unblock") >= 1


async def test_ai_console_shows_usage_per_feature_and_model_overrides_are_audited_and_reversible(
    client: httpx.AsyncClient, app, emulator_token, db_session
):
    from uuid import UUID

    from sqlalchemy import select

    from recruitai.ai import overrides
    from recruitai.ai.usage import AiCall
    from recruitai.config import AgentLLM

    overrides.invalidate()
    tag = uuid.uuid4().hex[:8]
    boss_email = f"boss-{tag}@example.test"
    base = get_settings().model_copy(update={"admin_emails": [boss_email]})
    app.dependency_overrides[get_settings] = lambda: base
    boss = {"Authorization": f"Bearer {_verified_token(f'uid-boss-{tag}', boss_email)}"}
    user = {
        "Authorization": f"Bearer {emulator_token(f'uid-ai-{tag}', f'ai-{tag}@example.test')}"
    }
    me = (await client.get("/api/v1/me", headers=user)).json()
    for ms, status in ((100, "ok"), (300, "ok"), (900, "error")):
        db_session.add(
            AiCall(
                org_id=UUID(me["active_org_id"]),
                user_id=UUID(me["user"]["id"]),
                feature="fit",
                model="m",
                prompt_version="fit@1",
                input_tokens=10,
                output_tokens=5,
                latency_ms=ms,
                status=status,
            )
        )
    await db_session.flush()

    assert (await client.get("/api/v1/admin/ai", headers=user)).status_code == 403
    console = (await client.get("/api/v1/admin/ai", headers=boss)).json()
    fit = next(f for f in console["features"] if f["feature"] == "fit")
    assert (fit["calls"], fit["errors"], fit["prompt_version"]) == (3, 1, "fit@1")
    assert (fit["input_tokens"], fit["output_tokens"], fit["overridden"]) == (
        30,
        15,
        False,
    )
    assert fit["p95_latency_ms"] >= fit["avg_latency_ms"] > 0
    assert {f["feature"] for f in console["features"]} >= {
        "cv_extract",
        "fit",
        "letter",
        "coach",
    }

    url = "/api/v1/admin/ai/fit"
    bad = await client.put(
        url, headers=boss, json={"provider": "gemini", "model": "gpt-9"}
    )
    assert bad.status_code == 422
    assert (
        await client.put(
            url, headers=user, json={"provider": "gemini", "model": "gemini-2.5-pro"}
        )
    ).status_code == 403
    ok = await client.put(
        url, headers=boss, json={"provider": "gemini", "model": "gemini-2.5-pro"}
    )
    assert ok.status_code == 204
    effective = await overrides.effective_settings(base, db_session)
    assert effective.agents["fit"] == AgentLLM(
        provider="gemini", model="gemini-2.5-pro"
    )
    assert (
        base.agents["fit"].model != "gemini-2.5-pro"
    )  # config.yaml itself is untouched

    assert (await client.delete(url, headers=boss)).status_code == 204
    back = await overrides.effective_settings(base, db_session)
    assert back.agents["fit"] == base.agents["fit"]
    changes = (await client.get("/api/v1/admin/ai", headers=boss)).json()["changes"]
    assert [(c["feature"], c["new_value"]) for c in changes[:2]] == [
        ("fit", None),
        ("fit", "gemini/gemini-2.5-pro"),
    ]
    assert (await db_session.execute(select(overrides.AiSetting))).scalars().all() == []
    overrides.invalidate()


async def test_prod_never_accepts_a_non_vertex_override(db_session):
    import pytest

    from recruitai.ai import overrides
    from recruitai.core.errors import ValidationFailed

    prod = get_settings().model_copy(update={"env": "prod", "qwen_model_name": "q"})
    assert "qwen" not in overrides.allowed_models(prod)
    with pytest.raises(ValidationFailed):
        await overrides.set_override(
            db_session,
            prod,
            feature="fit",
            provider="qwen",
            model="q",
            admin_user_id=None,
        )


async def test_a_failing_override_read_falls_back_to_config_and_does_not_break_the_session(
    db_session, monkeypatch
):
    from sqlalchemy import text

    from recruitai.ai import overrides
    from recruitai.config import get_settings as real_settings

    overrides.invalidate()

    def broken(*_a, **_k):
        raise RuntimeError("table missing")

    monkeypatch.setattr(overrides, "select", broken)
    settings = real_settings()

    effective = await overrides.effective_settings(settings, db_session)

    assert effective.agents == settings.agents  # config.yaml applies
    assert (
        await db_session.execute(text("SELECT 1"))
    ).scalar_one() == 1  # session still usable
    overrides.invalidate()
