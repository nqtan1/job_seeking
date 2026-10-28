"""/api/v1/signature through real HTTP: one signature per org, replaced not accumulated,
org-scoped, in the data export and gone with the account (ADR 0030)."""

import io
import zipfile

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from recruitai.core.storage import LocalStorage, ObjectNotFound
from tests.unit.test_signature import scan

URL = "/api/v1/signature"


async def _put(client, headers, data: bytes | None = None, name="sig.png"):
    return await client.put(
        URL, headers=headers, files={"file": (name, data or scan(), "image/png")}
    )


async def _keys(db_engine: AsyncEngine) -> list[str]:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT storage_key FROM documents WHERE kind = 'signature'")
        )
        return [r[0] for r in rows]


async def test_signature_lifecycle_replace_rotate_delete_and_org_isolation(
    real_client: httpx.AsyncClient,
    users,
    db_engine: AsyncEngine,
    fake_storage: LocalStorage,
):
    ada, bob = users["ada"], users["bob"]
    assert (await real_client.get(URL, headers=ada)).json() is None
    assert (await real_client.get(URL)).status_code == 401
    assert (
        await real_client.put(URL, files={"file": ("s.png", scan())})
    ).status_code == 401
    assert (
        await real_client.post(f"{URL}/rotate", json={"degrees": 90}, headers=ada)
    ).status_code == 404

    first = (await _put(real_client, ada)).json()
    assert first["issues"] == [] and first["limits"]["min_dpi"] == 200
    assert 20 <= first["recommended_width_mm"] <= 70
    png = (await real_client.get(first["url"])).content
    assert png.startswith(b"\x89PNG")
    [old_key] = await _keys(db_engine)
    assert old_key.startswith("orgs/") and "/signature/" in old_key

    second = (
        await _put(real_client, ada)
    ).json()  # replaced: old row and object are gone
    [new_key] = await _keys(db_engine)
    assert new_key != old_key and second["document_id"] != first["document_id"]
    with pytest.raises(ObjectNotFound):
        await fake_storage.get(old_key)

    # org B sees nothing of A's, and cannot rotate or delete it
    assert (await real_client.get(URL, headers=bob)).json() is None
    assert (
        await real_client.post(f"{URL}/rotate", json={"degrees": 90}, headers=bob)
    ).status_code == 404
    assert (await real_client.delete(URL, headers=bob)).status_code == 204
    assert (
        await real_client.get(f"/api/v1/documents/{second['document_id']}", headers=bob)
    ).status_code == 404
    assert await fake_storage.get(new_key)

    rotated = (
        await real_client.post(f"{URL}/rotate", json={"degrees": 90}, headers=ada)
    ).json()
    assert (rotated["width_px"], rotated["height_px"]) != (
        second["width_px"],
        second["height_px"],
    )
    assert len(await _keys(db_engine)) == 1
    assert (
        await real_client.post(f"{URL}/rotate", json={"degrees": 181}, headers=ada)
    ).status_code == 422
    docs = (await real_client.get("/api/v1/documents", headers=ada)).json()
    assert all(d["kind"] != "signature" for d in docs)  # not among the CVs and letters

    for bad in (b'<svg xmlns="http://www.w3.org/2000/svg"/>', b"nope"):
        assert (await _put(real_client, ada, bad)).status_code == 422
    assert (
        await _put(real_client, ada, b"%PDF-" + b"0" * (5 * 1024 * 1024))
    ).status_code == 422
    assert (await real_client.get(URL, headers=ada)).json()["document_id"] == rotated[
        "document_id"
    ]

    assert (await real_client.delete(URL, headers=ada)).status_code == 204
    assert (await real_client.get(URL, headers=ada)).json() is None
    assert await _keys(db_engine) == []
    with pytest.raises(ObjectNotFound):
        await fake_storage.get(new_key)


async def test_signature_is_in_the_data_export_and_removed_with_the_account(
    real_client: httpx.AsyncClient,
    users,
    db_engine: AsyncEngine,
    task_app,
    fake_storage: LocalStorage,
    monkeypatch,
):
    ada = users["ada"]
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)
    await _put(real_client, ada)
    [key] = await _keys(db_engine)

    export = await real_client.post("/api/v1/me/export", headers=ada)
    await task_app.run_worker_async(wait=False, install_signal_handlers=False)
    done = (await real_client.get(export.json()["status_url"], headers=ada)).json()
    archive = zipfile.ZipFile(
        io.BytesIO((await real_client.get(done["download_url"])).content)
    )
    assert any(n.startswith("files/signature/") for n in archive.namelist())

    assert (await real_client.delete("/api/v1/me", headers=ada)).status_code == 204
    with pytest.raises(ObjectNotFound):
        await fake_storage.get(key)
    assert await _keys(db_engine) == []
