"""``fit_analyses`` (ARCHITECTURE.md §4.3): one row per fit report. Re-running an analysis
inserts a new row (history, and the model/prompt may have changed), so there is no unique
constraint on ``(candidate_id, job_id)``. ``data`` holds ``FitCheck`` as JSONB; ``score`` and
``verdict`` are copies for sorting/filtering the job inbox."""

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class FitAnalysis(Base):
    __tablename__ = "fit_analyses"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score"),
        CheckConstraint("verdict IN ('go', 'maybe', 'no_go')", name="verdict"),
        CheckConstraint(
            "company_type IN ('corporate', 'startup', 'phd')", name="company_type"
        ),
        Index("ix_fit_analyses_org_id_created_at", "org_id", "created_at"),
        Index("ix_fit_analyses_org_id_job_id", "org_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    company_type: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
