"""User-defined helpers (ADR 0031). ``agents`` is the stable identity (UUID, avatar, name);
``agent_versions`` rows are immutable, so a run can pin the exact wording it used. Every row
carries ``org_id``."""

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
    UniqueConstraint,
    func,
    text,
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
            "char_length(instructions) BETWEEN 1 AND 4000", name="instructions"
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


class Flow(Base):
    __tablename__ = "flows"
    __table_args__ = (
        CheckConstraint("current_version >= 1", name="current_version"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="name"),
        Index("ix_flows_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, server_default="")
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


class FlowVersion(Base):
    """Immutable graph snapshot: a run pins one, so editing never disturbs a run."""

    __tablename__ = "flow_versions"
    __table_args__ = (
        UniqueConstraint("flow_id", "version"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_flow_versions_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FlowSchedule(Base):
    """ "Run this flow on its own, every hour / day / week" (ADR 0031). The user's own flow with the
    inputs they saved; it spends their daily AI quota like any run and pauses itself after repeated
    failures or when the account goes dormant."""

    __tablename__ = "flow_schedules"
    __table_args__ = (
        CheckConstraint("cadence IN ('hourly', 'daily', 'weekly')", name="cadence"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint(
            "paused_reason IN ('failures', 'inactive')", name="paused_reason"
        ),
        Index("ix_flow_schedules_org_id", "org_id"),
        Index("ix_flow_schedules_flow_id", "flow_id"),
        Index(  # the due-schedules sweep looks only at live ones
            "ix_flow_schedules_due",
            "next_run_at",
            postgresql_where=text("enabled AND paused_reason IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    cadence: Mapped[str] = mapped_column(String(8), nullable=False)
    at_time: Mapped[str | None] = mapped_column(String(5))  # "08:30", local time
    weekday: Mapped[int | None] = mapped_column(Integer)  # 0 = Monday
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    paused_reason: Mapped[str | None] = mapped_column(String(16))
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FlowRun(Base):
    __tablename__ = "flow_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'cancelled')",
            name="status",
        ),
        CheckConstraint("trigger IN ('manual', 'schedule')", name="trigger"),
        Index("ix_flow_runs_org_id_created_at", "org_id", "created_at"),
        Index("ix_flow_runs_flow_id_created_at", "flow_id", "created_at"),
        Index("ix_flow_runs_schedule_id_created_at", "schedule_id", "created_at"),
        Index(
            "ix_flow_runs_created_at", "created_at"
        ),  # the retention sweep, across orgs
        Index(  # the stuck-run sweep looks only at live runs
            "ix_flow_runs_running_updated_at",
            "updated_at",
            postgresql_where=text("status = 'running'"),
        ),
        Index(
            "uq_flow_runs_org_id_idempotency_key",
            "org_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    flow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )
    flow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flow_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="queued"
    )
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="manual"
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("flow_schedules.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Touched at every step: a run that stops moving is "stuck" and may be resumed.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FlowRunStep(Base):
    """Keyed by ``node_id``, never by agent: the same helper twice is two independent steps."""

    __tablename__ = "flow_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "node_id"),
        CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed', 'skipped')",
            name="status",
        ),
        Index("ix_flow_run_steps_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlowRunHandoff(Base):
    """What actually moved along one edge in one run (the inspector's "after the fact" view)."""

    __tablename__ = "flow_run_handoffs"
    __table_args__ = (
        UniqueConstraint("run_id", "edge_id"),
        Index("ix_flow_run_handoffs_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flow_runs.id", ondelete="CASCADE"), nullable=False
    )
    edge_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    from_node: Mapped[uuid.UUID] = mapped_column(nullable=False)
    to_node: Mapped[uuid.UUID] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
