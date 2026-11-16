"""GET /api/v1/tools (ADR 0039): the catalogue of the packs that are on."""

from dataclasses import replace

import httpx

from recruitai.config import get_settings
from recruitai.core import tools


async def test_get_tools_lists_the_packs_that_are_on(
    client: httpx.AsyncClient, emulator_token, monkeypatch
):
    ada = {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}
    r = await client.get("/api/v1/tools", headers=ada)
    assert r.status_code == 200
    by_id = {t["id"]: t for t in r.json()}
    assert set(by_id) == set(tools.all())
    assert by_id["send_email"] == {
        "id": "send_email",
        "pack": "messages",
        "inputs": [
            {"name": "to", "required": True},
            {"name": "subject", "required": True},
            {"name": "body", "required": True},
        ],
        "outputs": ["status"],
        "effect": "outside",
        "ai_uses": 0,
        "daily_cap": 20,
        "needs_job": False,
        "chat": False,
        "page": None,
    }

    # a pack behind a Settings flag (here the web pack, behind radar_enabled) disappears when it is off
    web = {
        k: replace(t, flag="radar_enabled")
        for k, t in tools.all().items()
        if t.pack == "web"
    }
    monkeypatch.setattr(tools, "_TOOLS", {**tools.all(), **web})
    off = get_settings().model_copy(update={"radar_enabled": False})
    client._transport.app.dependency_overrides[get_settings] = lambda: off  # type: ignore[attr-defined]
    r = await client.get("/api/v1/tools", headers=ada)
    assert {t["pack"] for t in r.json()} == {"career", "core", "messages"}
    client._transport.app.dependency_overrides.pop(get_settings)  # type: ignore[attr-defined]
