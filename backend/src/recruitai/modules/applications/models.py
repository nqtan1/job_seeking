"""``applications`` and ``application_events`` (ARCHITECTURE.md §4.3): the tracker and its
status timeline. An application may exist without a job from the inbox (``job_id`` NULL, and
``SET NULL`` if the job is deleted: it is the user's own record). Events are append-only and
repeat ``org_id`` so every query and the privacy deletion can filter by tenant directly."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id

_STATUSES = (
    "'to_apply', 'applied', 'in_review', 'interview', 'offer', 'rejected', 'ghosted'"
)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES})", name="status"),
        CheckConstraint(
            "source IN ('linkedin', 'indeed', 'france_travail', 'referral',"
            " 'company_site', 'other')",
            name="source",
        ),
        Index("ix_applications_org_id_created_at", "org_id", "created_at"),
        Index("ix_applications_org_id_status", "org_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    job_title: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="to_apply"
    )
    applied_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    __table_args__ = (
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUSES})", name="from_status"
        ),
        CheckConstraint(f"to_status IN ({_STATUSES})", name="to_status"),
        Index("ix_application_events_application_id_at", "application_id", "at"),
        Index("ix_application_events_org_id_at", "org_id", "at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # NULL for the creation event ("nothing" → first status).
    from_status: Mapped[str | None] = mapped_column(String)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class ApplicationDocument(Base):
    """A file the user attached to an application (the CV or letter PDF they actually sent).
    Deleting either side removes the link only; ``org_id`` is repeated for tenant filtering."""

    __tablename__ = "application_documents"
    __table_args__ = (Index("ix_application_documents_org_id", "org_id"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
