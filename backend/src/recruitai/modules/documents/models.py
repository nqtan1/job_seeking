"""``documents`` (ARCHITECTURE.md §4.3): one row per stored file; the bytes live in ``Storage``.

Tenant-owned: ``org_id`` + ``(org_id, created_at)`` index. ``storage_key`` is server-generated
(``orgs/{org_id}/{kind}/{uuid}``, never from a filename) and unique, so two rows can never
point at, and later delete, the same object.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('cv', 'jd', 'letter_pdf', 'attachment', 'export')", name="kind"
        ),
        CheckConstraint("size >= 0", name="size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        Index("ix_documents_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    mime: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL for system-generated files (rendered letter PDFs) and after the uploader is deleted.
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
