"""core/storage.py (P1-09): LocalStorage + the object_key/signature helpers.

GCSStorage is tested with a mocked client (never a real GCS call) in
tests/unit/test_gcs_storage.py.
"""

import time
from pathlib import Path
from uuid import uuid4

import pytest

from recruitai.core.storage import LocalStorage, ObjectNotFound, object_key


def test_object_key_shape():
    org_id = uuid4()
    key = object_key(org_id, "cv")
    assert key.startswith(f"orgs/{org_id}/cv/")
    assert key != object_key(org_id, "cv")  # a fresh uuid each call


async def test_put_get_delete_round_trip(tmp_path: Path):
    storage = LocalStorage(tmp_path, "secret")
    key = object_key(uuid4(), "cv")

    await storage.put(key, b"hello")
    assert await storage.get(key) == b"hello"

    await storage.delete(key)
    with pytest.raises(ObjectNotFound):
        await storage.get(key)


async def test_delete_prefix_removes_everything_under_it(tmp_path: Path):
    storage = LocalStorage(tmp_path, "secret")
    org_id = uuid4()
    a, b = object_key(org_id, "cv"), object_key(org_id, "jd")
    await storage.put(a, b"a")
    await storage.put(b, b"b")

    await storage.delete_prefix(f"orgs/{org_id}")

    with pytest.raises(ObjectNotFound):
        await storage.get(a)
    with pytest.raises(ObjectNotFound):
        await storage.get(b)


async def test_key_cannot_escape_the_storage_root(tmp_path: Path):
    storage = LocalStorage(tmp_path, "secret")
    with pytest.raises(ValueError, match="escapes"):
        await storage.get("../../etc/passwd")


async def test_signed_url_round_trip_and_tamper_and_expiry(tmp_path: Path):
    storage = LocalStorage(tmp_path, "secret")
    key = object_key(uuid4(), "cv")
    await storage.put(key, b"hello")

    url = await storage.signed_url(key, expires_in_s=60)
    path, _, query = url.partition("?")
    params = dict(p.split("=") for p in query.split("&"))
    assert path == f"/_dev/storage/{key}"
    assert storage.verify_signature(key, int(params["exp"]), params["sig"])

    assert not storage.verify_signature(
        key, int(params["exp"]), "tampered" + params["sig"]
    )
    assert not storage.verify_signature(key, int(time.time()) - 1, params["sig"])
