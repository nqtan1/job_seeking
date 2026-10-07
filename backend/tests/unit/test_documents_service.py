"""modules/documents/service.py (P1-10): upload validation, centralized once."""

from uuid import uuid4

import pytest

from recruitai.core.auth import CurrentUser
from recruitai.core.errors import ValidationFailed
from recruitai.core.storage import LocalStorage
from recruitai.core.tenancy import get_org_context
from recruitai.modules.documents.service import (
    MAX_UPLOAD_BYTES,
    sniff_mime,
    upload,
)

PDF_BYTES = b"%PDF-1.4\n%..."
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16
TXT_BYTES = b"just some plain text"
DOCX_BYTES = (
    b"PK\x03\x04" + b"\x00" * 16
)  # a real .docx is a zip; no sniffer matches it


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PDF_BYTES, "application/pdf"),
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (TXT_BYTES, "text/plain"),
        (DOCX_BYTES, None),
        (b"\x00\x01\x02binary-garbage", None),
    ],
)
def test_sniff_mime_uses_content_not_extension(data: bytes, expected: str | None):
    assert sniff_mime(data) == expected


async def test_upload_rejects_docx(db_session, fake_storage: LocalStorage):
    with pytest.raises(ValidationFailed):
        await upload(
            db_session,
            fake_storage,
            org_id=uuid4(),
            uploaded_by=uuid4(),
            kind="cv",
            data=DOCX_BYTES,
        )


async def test_upload_rejects_oversized_file(db_session, fake_storage: LocalStorage):
    with pytest.raises(ValidationFailed):
        await upload(
            db_session,
            fake_storage,
            org_id=uuid4(),
            uploaded_by=uuid4(),
            kind="cv",
            data=PDF_BYTES + b"0" * MAX_UPLOAD_BYTES,
        )


async def test_upload_rejects_disallowed_kind(db_session, fake_storage: LocalStorage):
    with pytest.raises(ValidationFailed):
        await upload(
            db_session,
            fake_storage,
            org_id=uuid4(),
            uploaded_by=uuid4(),
            kind="letter_pdf",  # system-generated only, not user-uploadable
            data=PDF_BYTES,
        )


async def test_upload_succeeds_and_stores_the_bytes(
    db_session, fake_storage: LocalStorage
):
    current = CurrentUser(
        firebase_uid=f"uid-doc-{uuid4().hex[:8]}", email="doc@example.test"
    )
    ctx = await get_org_context(current, db_session, x_org_id=None)

    document = await upload(
        db_session,
        fake_storage,
        org_id=ctx.org_id,
        uploaded_by=ctx.user_id,
        kind="cv",
        data=PDF_BYTES,
    )

    assert document.org_id == ctx.org_id
    assert document.mime == "application/pdf"
    assert document.size == len(PDF_BYTES)
    assert await fake_storage.get(document.storage_key) == PDF_BYTES
