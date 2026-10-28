"""Upload validation lives here, once (CLAUDE.md porting guide: legacy copied this per
feature — don't repeat that). No FastAPI imports (import-linter enforced via the module
list, same as every other service).
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.filenames import safe_filename
from recruitai.core.storage import ObjectNotFound, Storage, object_key
from recruitai.modules.documents import repository, signature
from recruitai.modules.documents.docx import docx_to_text, is_docx
from recruitai.modules.documents.models import Document
from recruitai.modules.documents.schemas import SignatureLimits, SignatureOut
from recruitai.modules.documents.signature_spec import (
    MAX_HEIGHT_MM,
    MAX_WIDTH_MM,
    MIN_DPI,
    MIN_WIDTH_MM,
    recommended_width_mm,
)
from recruitai.modules.documents.signature_spec import (
    MAX_UPLOAD_BYTES as MAX_SIGNATURE_BYTES,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_KINDS = frozenset(
    {"cv", "jd", "attachment"}
)  # letter_pdf, export and signature are system-generated only


_KIND_LABELS = {"cv": "CV", "jd": "job description"}
# Word files are accepted for these kinds and stored as their text (ADR 0027).
_TEXT_FROM_DOCX_KINDS = frozenset({"cv", "jd"})


def _looks_like_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


_SNIFFERS = (
    ("application/pdf", lambda d: d.startswith(b"%PDF-")),
    ("image/png", lambda d: d.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", lambda d: d.startswith(b"\xff\xd8\xff")),
    ("text/plain", _looks_like_text),
)


def sniff_mime(data: bytes) -> str | None:
    """Content, never extension or the client-declared Content-Type."""
    for mime, matches in _SNIFFERS:
        if matches(data):
            return mime
    return None


async def _store(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    uploaded_by: UUID | None,
    kind: str,
    data: bytes,
    mime: str | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> Document:
    """Size and content-type checks, then the object, then the row (no commit). ``mime`` is
    only passed for files the system itself generated (never for uploads): they are trusted,
    and a ZIP is not in the upload allowlist."""
    if len(data) > max_bytes:
        raise ValidationFailed("File exceeds the size limit.")
    mime = mime or sniff_mime(data)
    if mime is None:
        raise ValidationFailed("Unsupported or unrecognized file type.")

    # Storage first: an orphaned object on a failed DB write is harmless (swept later); a DB
    # row pointing at nothing would 404 on every future read.
    key = object_key(org_id, kind)
    await storage.put(key, data, content_type=mime)
    return await repository.create(
        db,
        org_id=org_id,
        kind=kind,
        storage_key=key,
        mime=mime,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by=uploaded_by,
    )


async def upload(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    uploaded_by: UUID | None,
    kind: str,
    data: bytes,
) -> Document:
    if kind not in ALLOWED_KINDS:
        raise ValidationFailed(f"kind must be one of {sorted(ALLOWED_KINDS)}.")
    if kind in _TEXT_FROM_DOCX_KINDS and is_docx(data):
        # Only the text is kept (ADR 0027): downstream code never sees a Word file.
        data = docx_to_text(data).encode()
    document = await _store(
        db, storage, org_id=org_id, uploaded_by=uploaded_by, kind=kind, data=data
    )
    await db.commit()
    return document


async def store_generated(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    kind: str,
    data: bytes,
    mime: str | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> Document:
    """A file the system made (a rendered letter PDF), as a ``documents`` row so retention and
    export treat it like any other. Same checks as an upload, but ``kind`` may be one only the
    system produces. The caller commits, together with whatever points at the document."""
    return await _store(
        db,
        storage,
        org_id=org_id,
        uploaded_by=None,
        kind=kind,
        data=data,
        mime=mime,
        max_bytes=max_bytes,
    )


async def get_document_with_url(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    document_id: UUID,
    filename: str | None = None,
    attachment: bool = False,
) -> tuple[Document, str]:
    document = await repository.get_by_id(db, org_id=org_id, document_id=document_id)
    if document is None:
        raise NotFound("Document not found.")
    if (
        document.kind == "export"
    ):  # the data-export ZIP always saves under a readable name
        filename = safe_filename(
            "RecruitAI data export", datetime.now(UTC).date().isoformat(), ext="zip"
        )
        attachment = True
    url = await storage.signed_url(
        document.storage_key, filename=filename, attachment=attachment
    )
    return document, url


async def list_documents(
    db: AsyncSession, *, org_id: UUID, kinds: list[str]
) -> list[Document]:
    return await repository.list_by_kinds(db, org_id=org_id, kinds=kinds)


async def read_document(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    document_id: UUID,
    kind: str | None = None,
) -> tuple[Document, bytes]:
    """Row + bytes, for other modules (e.g. CV extraction) that must not touch our SQL.
    ``kind`` is checked before the download, so a wrong-kind file costs no storage read."""
    document = await repository.get_by_id(db, org_id=org_id, document_id=document_id)
    if document is None:
        raise NotFound("Document not found.")
    if kind is not None and document.kind != kind:
        raise ValidationFailed(f"The document is not a {_KIND_LABELS.get(kind, kind)}.")
    return document, await storage.get(document.storage_key)


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, Any]]]:
    """The metadata rows of every file the org has (the bytes come from ``iter_files``)."""
    return {"documents": rows_as_dicts(await repository.all_for_org(db, org_id=org_id))}


async def iter_files(
    db: AsyncSession, storage: Storage, *, org_id: UUID
) -> AsyncIterator[tuple[Document, bytes | None]]:
    """Every file of the org, one at a time (never all in memory). ``None`` for a row whose
    object is gone from storage: the export records it instead of failing."""
    for document in await repository.all_for_org(db, org_id=org_id):
        if document.kind == "export":
            continue  # a previous export is not part of the user's data
        try:
            yield document, await storage.get(document.storage_key)
        except ObjectNotFound:
            yield document, None


async def delete_generated(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    kind: str,
    keep: UUID | None = None,
) -> None:
    """Remove the org's system-generated documents of ``kind`` other than ``keep`` (rows and
    objects). Call it *after* the replacement is stored: if storing fails, the old file must
    still be there."""
    for key in await repository.delete_of_kind(db, org_id=org_id, kind=kind, keep=keep):
        await storage.delete(key)


async def delete_document(
    db: AsyncSession, storage: Storage, *, org_id: UUID, document_id: UUID
) -> None:
    """Remove one file (row and object). Missing is fine: the goal is that it is gone."""
    document = await repository.get_by_id(db, org_id=org_id, document_id=document_id)
    if document is None:
        return
    key = document.storage_key
    await db.delete(document)
    await db.flush()
    await storage.delete(key)


async def sweep_older_than(
    db: AsyncSession, storage: Storage, *, kind: str, cutoff: datetime
) -> int:
    """Retention sweep for system-generated files of one kind (data-export ZIPs after 24 h):
    the object first, then the row."""
    documents_to_delete = await repository.older_of_kind(db, kind=kind, cutoff=cutoff)
    for document in documents_to_delete:
        await storage.delete(document.storage_key)
        await db.delete(document)
    await db.commit()
    return len(documents_to_delete)


# --- the user's signature image (ADR 0030): one per org, kind "signature" ---------------


async def _signature_out(
    storage: Storage, document: Document, png: bytes
) -> SignatureOut:
    analysis = signature.analyse(png)
    return SignatureOut(
        document_id=document.id,
        url=await storage.signed_url(document.storage_key),
        width_px=analysis.width_px,
        height_px=analysis.height_px,
        aspect=analysis.aspect,
        issues=signature.upload_issues(analysis),
        recommended_width_mm=recommended_width_mm(analysis.aspect),
        limits=SignatureLimits(
            min_width_mm=MIN_WIDTH_MM,
            max_width_mm=MAX_WIDTH_MM,
            max_height_mm=MAX_HEIGHT_MM,
            min_dpi=MIN_DPI,
        ),
    )


async def _replace_signature(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    user_id: UUID | None,
    png: bytes,
) -> SignatureOut:
    # One writer per org at a time (released at commit): two concurrent replacements would
    # otherwise each delete the other's new row and leave the org with none.
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(str(org_id), 0)))
    )
    document = await _store(
        db,
        storage,
        org_id=org_id,
        uploaded_by=user_id,
        kind="signature",
        data=png,
        mime="image/png",
    )
    # Commit the new row before removing the old object: a failure leaves a harmless orphan
    # object, never a signature row pointing at nothing.
    old_keys = await repository.delete_of_kind(
        db, org_id=org_id, kind="signature", keep=document.id
    )
    await db.commit()
    for key in old_keys:
        await storage.delete(key)
    return await _signature_out(storage, document, png)


async def get_signature(
    db: AsyncSession, storage: Storage, *, org_id: UUID
) -> SignatureOut | None:
    found = await signature_for_render_row(db, storage, org_id=org_id)
    if found is None:
        return None
    document, png = found
    return await _signature_out(storage, document, png)


async def signature_for_render_row(
    db: AsyncSession, storage: Storage, *, org_id: UUID
) -> tuple[Document, bytes] | None:
    document = await repository.get_of_kind(db, org_id=org_id, kind="signature")
    if document is None:
        return None
    try:
        return document, await storage.get(document.storage_key)
    except ObjectNotFound:
        return None


async def set_signature(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    user_id: UUID | None,
    data: bytes,
) -> SignatureOut:
    if len(data) > MAX_SIGNATURE_BYTES:
        raise ValidationFailed("File exceeds the size limit.")
    png = await asyncio.to_thread(signature.normalise, data)
    return await _replace_signature(
        db, storage, org_id=org_id, user_id=user_id, png=png
    )


async def rotate_signature(
    db: AsyncSession, storage: Storage, *, org_id: UUID, degrees: int
) -> SignatureOut:
    found = await signature_for_render_row(db, storage, org_id=org_id)
    if found is None:
        raise NotFound("No signature.")
    document, png = found
    rotated = await asyncio.to_thread(signature.rotate, png, degrees)
    return await _replace_signature(
        db, storage, org_id=org_id, user_id=document.uploaded_by, png=rotated
    )


async def delete_signature(db: AsyncSession, storage: Storage, *, org_id: UUID) -> None:
    await delete_generated(db, storage, org_id=org_id, kind="signature")
    await db.commit()


async def signature_for_render(
    db: AsyncSession, storage: Storage, *, org_id: UUID
) -> tuple[bytes, float] | None:
    """(PNG bytes, width / height) for the letter renderer; ``None`` when there is none."""
    found = await signature_for_render_row(db, storage, org_id=org_id)
    if found is None:
        return None
    png = found[1]
    return png, signature.analyse(png).aspect
