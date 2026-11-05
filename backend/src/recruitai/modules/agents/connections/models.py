"""A user's link to an outside account (ADR 0036)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class Connection(Base):
    """A user's link to an outside account (ADR 0036): one per user per provider. Telegram: pending
    until the person sends the one-time code to the platform bot, then active with their chat id.
    ``link_hash`` is the hash of that code; nothing here is a credential."""

    __tablename__ = "connections"
    __table_args__ = (
        CheckConstraint("provider IN ('telegram')", name="provider"),
        CheckConstraint("status IN ('pending', 'active')", name="status"),
        UniqueConstraint("user_id", "provider"),
        Index("ix_connections_org_id", "org_id"),
        Index("ix_connections_link_hash", "link_hash"),
        Index(  # one account per chat, even when two polls race
            "uq_connections_active_chat",
            "provider",
            "chat_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    link_hash: Mapped[str | None] = mapped_column(String(64))
    link_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
