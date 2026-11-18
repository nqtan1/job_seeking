"""``conversations``, ``messages`` (ADR 0016) and ``coach_actions`` (ADR 0042). ``org_id`` is repeated
so queries and privacy deletion filter by tenant directly; a conversation outlives its job (``SET NULL``)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_org_id_started_at", "org_id", "started_at"),
        CheckConstraint("kind IN ('chat', 'assistant')", name="kind"),
        Index(  # one Assistant conversation per org (orgs are personal, ADR 0008)
            "uq_conversations_org_id_assistant",
            "org_id",
            unique=True,
            postgresql_where=text("kind = 'assistant'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    # the helper chatted with (ADR 0039); null = the default coach
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL")
    )
    # 'assistant': the inbox where run results and reminders land (ADR 0042, ``coach/inbox.py``)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="chat")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        Index(
            "ix_messages_conversation_id_created_at", "conversation_id", "created_at"
        ),
        Index("ix_messages_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Assistant rows only: what the reply was grounded in (``schemas.MessageMeta``, schema_version 1).
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CoachAction(Base):
    """A write (or AI-spending) tool call the chat proposed: it runs only when the user confirms
    it (``POST .../actions/{id}``). ``args`` are the tool's inputs as checked text; ``summary`` is
    built by the server, never by the model. Goes with its conversation."""

    __tablename__ = "coach_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'done', 'cancelled', 'failed', 'expired')",
            name="status",
        ),
        Index("ix_coach_actions_org_id_conversation_id", "org_id", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    # the job in focus when it was proposed: confirm runs on that job, whatever is in focus then
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    untrusted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    code: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
