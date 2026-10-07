"""Upload validation lives here, once (CLAUDE.md porting guide: legacy copied this per
feature — don't repeat that). No FastAPI imports (import-linter enforced via the module
list, same as every other service).
"""

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.filenames import safe_filename
from recruitai.core.storage import ObjectNotFound, Storage, object_key
from recruitai.modules.documents import repository
from recruitai.modules.documents.models import Document

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_KINDS = frozenset(
    {"cv", "jd", "attachment"}
)  # letter_pdf is system-generated only


_KIND_LABELS = {"cv": "CV", "jd": "job description"}


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
