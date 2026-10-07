"""Identity tables (ARCHITECTURE.md §4.3, ADR 0008): organizations, users, memberships.

``role`` and ``kind`` are constrained varchars, not native Postgres enums: adding a value is
an ordinary migration instead of ``ALTER TYPE`` (expand/contract friendly).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (CheckConstraint("kind IN ('personal', 'company')", name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    # UNIQUE: P1-07 provisions users with an atomic INSERT ... ON CONFLICT (firebase_uid).
    firebase_uid: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set by an admin: every request of a blocked user is refused (core/tenancy.py).
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Daily digest of follow-ups and interviews (identity/service.send_application_reminders).
    email_reminders: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id"),
        CheckConstraint("role IN ('owner', 'recruiter', 'member')", name="role"),
        Index("ix_memberships_org_id_created_at", "org_id", "created_at"),
        Index("ix_memberships_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdminAction(Base):
    """Who did what to whom (ADR 0019): ids only, no personal data. The ids go to NULL if either
    user is deleted, so the row never keeps anyone's identity."""

    __tablename__ = "admin_actions"
    __table_args__ = (CheckConstraint("action IN ('block', 'unblock')", name="action"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
