"""Job radar tables (ADR 0021): saved searches, what each run did, and every job the radar has
looked at. ``radar_results`` doubles as the "seen" ledger, so a job is never scored twice; its
``job_id`` is NULL once a below-threshold job has been taken back out of the user's inbox. Every
row carries ``org_id`` so each query (and the privacy deletion) filters by tenant directly."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class RadarSearch(Base):
    __tablename__ = "radar_searches"
    __table_args__ = (
        CheckConstraint("min_score BETWEEN 0 AND 100", name="min_score"),
        CheckConstraint("daily_limit BETWEEN 1 AND 10", name="daily_limit"),
        Index("ix_radar_searches_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    query: Mapped[str | None] = mapped_column(String)
    department: Mapped[str | None] = mapped_column(String)
    contract_type: Mapped[str | None] = mapped_column(String)
    min_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="70")
    daily_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="5"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When a run was last asked for: tells "queued, not started yet" from "finished".
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RadarResult(Base):
    __tablename__ = "radar_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'approved', 'dismissed', 'skipped')", name="status"
        ),
        UniqueConstraint("org_id", "source", "external_id"),
        Index("ix_radar_results_org_id_status", "org_id", "status"),
        Index("ix_radar_results_search_id_found_at", "search_id", "found_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    search_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("radar_searches.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_postings.id", ondelete="SET NULL")
    )
    score: Mapped[float | None] = mapped_column(Float)
    # Kept on the result (not read from the job) so they survive a removed job: what the user
    # sees for a match and for a job that was checked but not shortlisted.
    title: Mapped[str | None] = mapped_column(String)
    company: Mapped[str | None] = mapped_column(String)
    # {"strengths": [...], "gaps": [...], "missing": [...], "summary": str | None}
    highlights: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="new")
    # Set once the user has looked at the match list: the menu badge counts only unseen ones.
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RadarRun(Base):
    """What one run did: the user's activity log ("what your radar did")."""

    __tablename__ = "radar_runs"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'partial', 'error')", name="status"),
        Index("ix_radar_runs_org_id_started_at", "org_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    search_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("radar_searches.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ok")
    # Why it stopped: done | limit | quota | no_profile | ai_unavailable | provider_error
    stop_reason: Mapped[str | None] = mapped_column(String)
    found: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    added: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    scored: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    shortlisted: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    error_code: Mapped[str | None] = mapped_column(String)
