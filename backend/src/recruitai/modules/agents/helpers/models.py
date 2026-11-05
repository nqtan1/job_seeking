"""User-defined helpers (ADR 0031): the stable ``agents`` identity and its immutable ``agent_versions``."""

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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("current_version >= 1", name="current_version"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="name"),
        Index("ix_agents_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    avatar: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Compare-and-set target for edits (a stale editor gets 409, never an overwrite).
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint("agent_id", "version"),
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint(
            "char_length(instructions) <= 4000 AND (role <> 'custom' OR char_length(instructions) >= 1)",
            name="instructions",
        ),
        CheckConstraint(
            "role IN ('custom', 'letter', 'interview', 'cv_advice')", name="role"
        ),
        CheckConstraint("model_tier IN ('fast', 'smart')", name="model_tier"),
        Index("ix_agent_versions_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="custom"
    )
    instructions: Mapped[str] = mapped_column(String, nullable=False)
    model_tier: Mapped[str] = mapped_column(String(8), nullable=False)
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    context_sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    output_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
