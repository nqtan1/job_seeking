"""GCSStorage (P1-09): a mocked google-cloud-storage client — never a real GCS call."""

from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound as GcsNotFound

from recruitai.core.storage import GCSStorage, ObjectNotFound


def _bucket_with_blob() -> tuple[MagicMock, MagicMock]:
    blob = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob
    return bucket, blob


async def test_put_uploads_bytes_with_content_type():
    bucket, blob = _bucket_with_blob()
    storage = GCSStorage(bucket)

    await storage.put("orgs/x/cv/y", b"data", content_type="application/pdf")

    bucket.blob.assert_called_once_with("orgs/x/cv/y")
    blob.upload_from_string.assert_called_once_with(
        b"data", content_type="application/pdf"
    )


async def test_get_returns_bytes():
    bucket, blob = _bucket_with_blob()
    blob.download_as_bytes.return_value = b"data"
    storage = GCSStorage(bucket)

    assert await storage.get("orgs/x/cv/y") == b"data"


async def test_get_missing_object_raises_object_not_found():
    bucket, blob = _bucket_with_blob()
    blob.download_as_bytes.side_effect = GcsNotFound("gone")
    storage = GCSStorage(bucket)

    with pytest.raises(ObjectNotFound):
        await storage.get("orgs/x/cv/y")


async def test_signed_url_delegates_to_the_sdk():
    bucket, blob = _bucket_with_blob()
    blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed"
    storage = GCSStorage(bucket)

    url = await storage.signed_url("orgs/x/cv/y", expires_in_s=120)

    assert url == "https://storage.googleapis.com/signed"
    assert blob.generate_signed_url.call_args.kwargs["method"] == "GET"


async def test_signed_url_signs_through_iam_with_the_runtime_account():
    # Cloud Run credentials have no private key: the SDK needs the account email + a token.
    bucket, blob = _bucket_with_blob()
    creds = bucket.client._credentials
    creds.service_account_email = "api@p.iam.gserviceaccount.com"
    creds.token = "tok"
    storage = GCSStorage(bucket)

    await storage.signed_url("orgs/x/cv/y")

    creds.refresh.assert_called_once()
    kwargs = blob.generate_signed_url.call_args.kwargs
    assert kwargs["service_account_email"] == "api@p.iam.gserviceaccount.com"
    assert kwargs["access_token"] == "tok"


async def test_delete_prefix_deletes_every_matching_blob():
    bucket, _ = _bucket_with_blob()
    blob_a, blob_b = MagicMock(), MagicMock()
    bucket.list_blobs.return_value = [blob_a, blob_b]
    storage = GCSStorage(bucket)

    await storage.delete_prefix("orgs/x/")

    bucket.list_blobs.assert_called_once_with(prefix="orgs/x/")
    blob_a.delete.assert_called_once()
    blob_b.delete.assert_called_once()
