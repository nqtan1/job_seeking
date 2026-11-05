"""Email recipients, suppressions and invites (ADR 0032)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class EmailRecipient(Base):
    """An address a user may email from a flow, confirmed by the address's owner (ADR 0032).
    ``confirm_hash`` is the hash of the one-time link token; ``unsubscribe_token`` is what every
    message's unsubscribe link carries."""

    __tablename__ = "email_recipients"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'confirmed')", name="status"),
        UniqueConstraint("user_id", "email"),
        UniqueConstraint("unsubscribe_token"),
        Index("ix_email_recipients_org_id", "org_id"),
        Index("ix_email_recipients_confirm_hash", "confirm_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    confirm_hash: Mapped[str | None] = mapped_column(String(64))
    unsubscribe_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailSuppression(Base):
    """Addresses that said "stop", for the whole platform. Only a hash: no address is kept."""

    __tablename__ = "email_suppressions"

    email_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmailInvite(Base):
    """One confirmation mail sent to an address, by someone: the ledger the caps count. Never
    deleted when a contact is removed (add, remove, add again must not be a free mail machine).
    Only a hash of the address."""

    __tablename__ = "email_invites"
    __table_args__ = (
        Index("ix_email_invites_user_id_created_at", "user_id", "created_at"),
        Index("ix_email_invites_email_hash_created_at", "email_hash", "created_at"),
        Index("ix_email_invites_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
