"""Radar DTOs (ADR 0021). Search settings are bounded here and again by DB CHECK constraints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ResultStatus = Literal["new", "approved", "dismissed", "skipped"]
MAX_SEARCHES_PER_ORG = 3


class RadarSearchIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    query: str | None = Field(None, max_length=200)
    department: str | None = Field(
        None,
        max_length=60,
        description="Departments or cities, comma-separated: 75, 69 or Paris, Lyon",
    )
    contract_type: str | None = Field(
        None,
        max_length=60,
        description="Contract codes, comma-separated: CDI,CDD (empty = all)",
    )
    min_score: int = Field(70, ge=0, le=100)
    daily_limit: int = Field(5, ge=1, le=10, description="Jobs scored per day, at most")
    enabled: bool = True


class RadarSearchOut(RadarSearchIn):
    id: UUID
    last_run_at: datetime | None
    created_at: datetime


class Highlights(BaseModel):
    """Why the job did or did not match: a few lines the user can read at a glance."""

    strengths: list[str] = []
    gaps: list[str] = []
    missing: list[str] = []
    summary: str | None = None


class RadarResultOut(BaseModel):
    id: UUID
    search_id: UUID
    search_name: str | None = None
    job_id: UUID | None
    score: float | None
    status: ResultStatus
    found_at: datetime
    title: str | None = None
    company: str | None = None
    highlights: Highlights = Highlights()
    # The tracker's status once the user has applied (the radar's story does not end at "keep")
    application_status: str | None = None


class RadarRunOut(BaseModel):
    id: UUID
    search_id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: Literal["ok", "partial", "error"]
    stop_reason: str | None
    found: int
    added: int
    scored: int
    shortlisted: int


class RadarSearchUpdate(BaseModel):
    """PATCH: only the fields sent change."""

    name: str | None = Field(None, min_length=1, max_length=100)
    query: str | None = Field(None, max_length=200)
    department: str | None = Field(None, max_length=60)
    contract_type: str | None = Field(None, max_length=60)
    min_score: int | None = Field(None, ge=0, le=100)
    daily_limit: int | None = Field(None, ge=1, le=10)
    enabled: bool | None = None


class RunAccepted(BaseModel):
    task_id: UUID
    status_url: str


class AiUseOut(BaseModel):
    used: int
    quota: int
    radar_stops_at: int


class KeepOut(BaseModel):
    job_id: UUID


class Funnel(BaseModel):
    """The last 30 days, from the radar's results to the tracker."""

    scored: int
    shortlisted: int
    approved: int
    applied: int
    interviews: int


class MissingItem(BaseModel):
    text: str
    count: int


class InsightsOut(BaseModel):
    days: int
    funnel: Funnel
    average_score: float | None
    most_missing: list[MissingItem]


class RadarStatusOut(BaseModel):
    new_matches: int
    searches: int
    daily_searches: int
    running: bool
    last_run: RadarRunOut | None
    next_run_at: datetime | None
    # The last run could not finish (AI or job source down, a crash): it can be retried at once
    interrupted: bool = False
    interrupted_reason: str | None = None
