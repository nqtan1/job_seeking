"""All SQL for the documents module. Every query filters by org_id."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.documents.models import Document


async def create(
    session: AsyncSession,
    *,
    org_id: UUID,
    kind: str,
    storage_key: str,
    mime: str,
    size: int,
    sha256: str,
    uploaded_by: UUID | None,
) -> Document:
    document = Document(
        org_id=org_id,
        kind=kind,
        storage_key=storage_key,
        mime=mime,
        size=size,
        sha256=sha256,
        uploaded_by=uploaded_by,
    )
    session.add(document)
    await session.flush()
    return document


async def get_by_id(
    session: AsyncSession, *, org_id: UUID, document_id: UUID
) -> Document | None:
    return (
        await session.execute(
            select(Document).where(
                Document.id == document_id, Document.org_id == org_id
            )
        )
    ).scalar_one_or_none()


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[Document]:
    rows = await session.execute(
        select(Document).where(Document.org_id == org_id).order_by(Document.created_at)
    )
    return list(rows.scalars())


async def list_by_kinds(
    session: AsyncSession, *, org_id: UUID, kinds: list[str]
) -> list[Document]:
    rows = await session.execute(
        select(Document)
        .where(Document.org_id == org_id, Document.kind.in_(kinds))
        .order_by(Document.created_at.desc())
    )
    return list(rows.scalars())


async def delete_of_kind(
    session: AsyncSession, *, org_id: UUID, kind: str, keep: UUID | None
) -> list[str]:
    """Delete the org's documents of one kind except ``keep``; returns their storage keys (to
    delete the objects)."""
    stmt = select(Document).where(Document.org_id == org_id, Document.kind == kind)
    if keep is not None:
        stmt = stmt.where(Document.id != keep)
    rows = await session.execute(stmt)
    keys = []
    for document in rows.scalars():
        keys.append(document.storage_key)
        await session.delete(document)
    await session.flush()
    return keys


async def older_of_kind(
    session: AsyncSession, *, kind: str, cutoff: datetime
) -> list[Document]:
    rows = await session.execute(
        select(Document).where(Document.kind == kind, Document.created_at < cutoff)
    )
    return list(rows.scalars())
