"""``job_postings`` and ``job_search_cache`` (ARCHITECTURE.md §4.3).

``job_postings`` is the user's job inbox: ``data`` holds ``JobPosition`` as JSONB (bump
``schema_version`` when its shape changes, no migration needed). ``external_id`` is the
provider's id for ``france_travail`` rows; manual and file rows have none, and Postgres treats
NULLs as distinct in the unique constraint, so the same text can be saved twice on purpose.

``job_search_cache`` holds public provider responses keyed by the query, shared across orgs
and deliberately without ``org_id``: nothing personal is stored in it, and a per-org cache
would defeat the point (France Travail rate limits). Rows expire after 24 h.
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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.core.db import Base
from recruitai.core.ids import new_id


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'file', 'france_travail')", name="source"
        ),
        UniqueConstraint("org_id", "source", "external_id"),
        Index("ix_job_postings_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String)
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str | None] = mapped_column(String)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class JobSearchCache(Base):
    __tablename__ = "job_search_cache"
    # The retention sweep (P2-31) deletes by expiry.
    __table_args__ = (Index("ix_job_search_cache_expires_at", "expires_at"),)

    key: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
