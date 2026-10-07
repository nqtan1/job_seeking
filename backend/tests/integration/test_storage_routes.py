"""Dev-only signed-download route (P1-09), through real HTTP via the ``client`` fixture —
proves the route resolves storage through ``dependency_overrides`` like any other route,
not a baked-in instance from app construction."""

import time
from uuid import uuid4

import httpx

from recruitai.core.storage import LocalStorage, object_key, sign_local_key


async def test_valid_signed_url_downloads_the_object(
    client: httpx.AsyncClient, fake_storage: LocalStorage
):
    key = object_key(uuid4(), "cv")
    await fake_storage.put(key, b"pdf-bytes")
    url = await fake_storage.signed_url(key)

    resp = await client.get(url)

    assert resp.status_code == 200
    assert resp.content == b"pdf-bytes"


async def test_tampered_signature_is_401(
    client: httpx.AsyncClient, fake_storage: LocalStorage
):
    key = object_key(uuid4(), "cv")
    await fake_storage.put(key, b"pdf-bytes")
    url = await fake_storage.signed_url(key)

    resp = await client.get(url + "tampered")

    assert resp.status_code == 401


async def test_expired_signature_is_401(
    client: httpx.AsyncClient, fake_storage: LocalStorage
):
    key = object_key(uuid4(), "cv")
    await fake_storage.put(key, b"pdf-bytes")
    exp = int(time.time()) - 10
    sig = sign_local_key(key, exp, fake_storage.signing_secret)

    resp = await client.get(f"/_dev/storage/{key}?exp={exp}&sig={sig}")

    assert resp.status_code == 401


async def test_valid_signature_for_a_missing_object_is_404(
    client: httpx.AsyncClient, fake_storage: LocalStorage
):
    key = object_key(uuid4(), "cv")
    url = await fake_storage.signed_url(key)  # never put()

    resp = await client.get(url)

    assert resp.status_code == 404
