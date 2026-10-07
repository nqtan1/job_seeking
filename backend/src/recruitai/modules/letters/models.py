"""``letters`` and ``letter_versions`` (ARCHITECTURE.md §4.3, §10.3).

``content`` holds ``LetterContent`` as JSONB (bump ``schema_version`` when its shape changes).
A letter outlives its job posting (``job_id`` is ``SET NULL``): it is the user's own work.
There is deliberately no expiry column or sweep hook: a draft is an ordinary letter, only
temporary preview PDFs expire (GCS ``tmp/`` lifecycle rule, §4.7/§11.2).

``letter_versions`` is the history of ``content`` (PK ``(letter_id, n)``). ``org_id`` is
repeated on it so every query, and the privacy deletion, can filter by tenant directly.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class Letter(Base):
    __tablename__ = "letters"
    __table_args__ = (
        CheckConstraint("kind IN ('cover')", name="kind"),
        CheckConstraint(
            "template IN ('classic', 'modern', 'compact', 'lettre_fr')", name="template"
        ),
        CheckConstraint("language IN ('fr', 'en')", name="language"),
        CheckConstraint(
            "tone IN ('professional', 'warm', 'confident', 'academic', 'formal')",
            name="tone",
        ),
        CheckConstraint("length IN ('short', 'standard', 'detailed')", name="length"),
        CheckConstraint(
            "company_type IN ('corporate', 'startup', 'phd')", name="company_type"
        ),
        CheckConstraint("status IN ('draft', 'final')", name="status"),
        CheckConstraint(
            "render_status IN ('none', 'queued', 'done', 'failed')",
            name="render_status",
        ),
        Index("ix_letters_org_id_created_at", "org_id", "created_at"),
        Index("ix_letters_org_id_job_id", "org_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String, nullable=False, server_default="cover")
    template: Mapped[str] = mapped_column(
        String, nullable=False, server_default="classic"
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # "Eject to raw LaTeX" (§10.1): when set, the template is skipped.
    latex_override: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String, nullable=False)
    tone: Mapped[str] = mapped_column(String, nullable=False)
    length: Mapped[str] = mapped_column(String, nullable=False)
    company_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="draft")
    render_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="none"
    )
    # The rendered PDF is a ``documents`` row (kind 'letter_pdf'), so retention applies to it.
    pdf_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LetterVersion(Base):
    __tablename__ = "letter_versions"
    __table_args__ = (
        Index("ix_letter_versions_org_id_created_at", "org_id", "created_at"),
    )

    letter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("letters.id", ondelete="CASCADE"), primary_key=True
    )
    n: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
