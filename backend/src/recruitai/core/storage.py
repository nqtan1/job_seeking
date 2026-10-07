"""File storage (ARCHITECTURE.md §4.8, §6): a ``Storage`` protocol, ``LocalStorage`` (dev/
test, the default) and ``GCSStorage`` (prod). Framework-free — see ``core/storage_routes.py``
for the dev-only signed-download route, split out the same way ``core/error_handlers.py`` is
split from ``core/errors.py``, so services can import this module without pulling in FastAPI.

Keys are always server-generated (``orgs/{org_id}/{kind}/{uuid}``) via ``object_key()``: no
code path may build one from a filename or any other client-supplied string.
"""

import hashlib
import hmac
import logging
import shutil
import time
from datetime import timedelta
from functools import lru_cache, partial
from pathlib import Path
from typing import Protocol
from urllib.parse import quote
from uuid import UUID

from anyio.to_thread import run_sync

from recruitai.config import Settings, get_settings
from recruitai.core.filenames import content_disposition
from recruitai.core.ids import new_id

logger = logging.getLogger(__name__)


def object_key(org_id: UUID, kind: str, object_id: UUID | None = None) -> str:
    return f"orgs/{org_id}/{kind}/{object_id or new_id()}"


class ObjectNotFound(Exception):
    pass


class Storage(Protocol):
    async def put(self, key: str, data: bytes, *, content_type: str = "") -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def signed_url(
        self,
        key: str,
        *,
        expires_in_s: int = 900,
        filename: str | None = None,
        attachment: bool = False,
    ) -> str: ...
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> None: ...


def sign_local_key(key: str, exp: int, secret: str) -> str:
    message = f"{key}:{exp}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_local_signature(key: str, exp: int, sig: str, secret: str) -> bool:
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sign_local_key(key, exp, secret), sig)


class LocalStorage:
    """Dev/test only. Files live under ``root``. ``signed_url()`` returns a relative URL
    (same-origin as the API, per the dev Vite proxy) pointing at the dev-only download route,
    which independently re-verifies the signature and expiry before streaming anything."""

    def __init__(self, root: Path, signing_secret: str) -> None:
        self.root = root.resolve()
        self.signing_secret = signing_secret

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"key escapes the storage root: {key!r}")
        return path

    async def put(self, key: str, data: bytes, *, content_type: str = "") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise ObjectNotFound(key) from None

    async def signed_url(
        self,
        key: str,
        *,
        expires_in_s: int = 900,
        filename: str | None = None,
        attachment: bool = False,
    ) -> str:
        exp = int(time.time()) + expires_in_s
        sig = sign_local_key(key, exp, self.signing_secret)
        url = f"/_dev/storage/{key}?exp={exp}&sig={sig}"
        if filename:  # display-only: the route sanitizes it again
            url += f"&name={quote(filename)}&dl={int(attachment)}"
        return url

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def delete_prefix(self, prefix: str) -> None:
        base = self._path(prefix)
        shutil.rmtree(base, ignore_errors=True)

    def verify_signature(self, key: str, exp: int, sig: str) -> bool:
        return verify_local_signature(key, exp, sig, self.signing_secret)


class GCSStorage:
    """Prod. Wraps a ``google.cloud.storage.Bucket``. The SDK is synchronous, so every call
    runs in a thread (checklist item 12) — never on the event loop."""

    def __init__(self, bucket: object) -> None:
        self._bucket = bucket

    async def put(self, key: str, data: bytes, *, content_type: str = "") -> None:
        blob = self._bucket.blob(key)  # type: ignore[attr-defined]
        await run_sync(
            partial(blob.upload_from_string, data, content_type=content_type or None)
        )

    async def get(self, key: str) -> bytes:
        from google.api_core.exceptions import NotFound as GcsNotFound

        blob = self._bucket.blob(key)  # type: ignore[attr-defined]
        try:
            result: bytes = await run_sync(blob.download_as_bytes)
        except GcsNotFound:
            raise ObjectNotFound(key) from None
        return result

    async def signed_url(
        self,
        key: str,
        *,
        expires_in_s: int = 900,
        filename: str | None = None,
        attachment: bool = False,
    ) -> str:
        blob = self._bucket.blob(key)  # type: ignore[attr-defined]

        def sign() -> str:
            # Cloud Run has no private key: sign through the IAM API as the runtime service
            # account (it holds serviceAccountTokenCreator on itself, infra/run.tf).
            from google.auth.transport.requests import Request

            creds = self._bucket.client._credentials  # type: ignore[attr-defined]
            creds.refresh(Request())
            try:
                signed: str = blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(seconds=expires_in_s),
                    method="GET",
                    response_disposition=(
                        content_disposition(filename, attachment=attachment)
                        if filename
                        else None
                    ),
                    service_account_email=creds.service_account_email,
                    access_token=creds.token,
                )
            except Exception as exc:
                # IAM's reply (status + reason, no letter data): the type alone hides why.
                logger.error(
                    "gcs signing failed",
                    extra={
                        "error_type": type(exc).__name__,
                        "iam_error": str(exc)[:400],
                    },
                )
                raise
            return signed

        return await run_sync(sign)

    async def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)  # type: ignore[attr-defined]
        await run_sync(blob.delete)

    async def delete_prefix(self, prefix: str) -> None:
        blobs = await run_sync(
            partial(lambda: list(self._bucket.list_blobs(prefix=prefix)))  # type: ignore[attr-defined]
        )
        for blob in blobs:
            await run_sync(blob.delete)


def get_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        return LocalStorage(
            Path(settings.local_storage_root), settings.local_storage_signing_secret
        )
    from google.cloud import storage as gcs_sdk

    if not settings.gcs_bucket:
        raise ValueError("GCS_BUCKET is required when STORAGE_BACKEND=gcs")
    import google.auth

    # cloud-platform, not the SDK's default storage-only scope: signing a URL calls the IAM
    # signBlob API, which refuses a storage-scoped token (ACCESS_TOKEN_SCOPE_INSUFFICIENT).
    creds, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    client = gcs_sdk.Client(credentials=creds, project=project)
    return GCSStorage(client.bucket(settings.gcs_bucket))


@lru_cache
def get_storage_dependency() -> Storage:
    """FastAPI dependency: one Storage instance per process (a fresh GCS client per request
    would be wasteful; LocalStorage is cheap either way)."""
    return get_storage(get_settings())
