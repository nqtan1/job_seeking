"""``FitCheck`` is the LLM output schema for a fit analysis and the stored
``fit_analyses.data``. Moved from the legacy ``domain/fit/schema.py``.

Not ported: ``FitAnalysisRequest/Response`` (they carry file paths and recruiter fields; the
API takes a ``job_id`` and reads the caller's profile) and the interview-kit models (a
separate feature, not part of the fit report).

``key_missing_requirements``, ``confidence``, ``summary`` and ``constructive_feedback`` are
required (nullable where unknown): with optional fields the small self-hosted model skips
them under guided decoding, and ``summary``/``constructive_feedback`` are what the user reads.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

CompanyType = Literal["corporate", "startup", "phd"]


class Recommendation(StrEnum):
    GO = "go"
    MAYBE = "maybe"
    NO_GO = "no_go"


class FitCheck(BaseModel):
    """Structured fit assessment between a candidate's profile and a job, evaluated through
    a persona-specific lens (corporate / PhD / startup).

    Field order matters: guided decoding fills fields in schema order, so the reasoning
    (strengths, gaps, reasons) comes *before* the score and verdict. With the verdict first,
    the small self-hosted model committed to a score with no reasoning behind it."""

    strengths: list[str] = Field(
        ...,
        description="Concrete strengths of the candidate relative to this job, framed using the persona's focus areas and vocabulary.",
    )
    gaps: list[str] = Field(
        ...,
        description="Concrete gaps, risks, or red flags identified, framed the way this persona would flag them (e.g. seniority mismatch, topic misalignment, lack of ownership evidence).",
    )
    key_missing_requirements: list[str] = Field(
        ...,
        description="Specific hard requirements from the job description that the candidate does not appear to meet (e.g. missing certification, required years of experience, specific tool/language). Empty list if none.",
    )
    reasons: list[str] = Field(
        ...,
        description="List of reasons supporting the overall verdict — combines both why the candidate fits and why they might not, in priority order.",
    )
    fit_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Overall fit score from 0 to 100, calibrated to the specific persona's evaluation logic (corporate/PhD/startup criteria differ).",
    )
    recommendation: Recommendation = Field(
        ...,
        description="Final hiring recommendation: 'go', 'maybe', or 'no_go', matching the reasoning a real recruiter in this persona would give.",
    )
    is_fit: bool = Field(
        ...,
        description="Overall boolean verdict: True if the candidate is a viable fit for this role, False otherwise.",
    )
    confidence: float | None = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model's confidence in this assessment (0.0-1.0), lower if the CV or job description had missing/ambiguous information.",
    )
    summary: str | None = Field(
        ...,
        description="1-3 sentence executive summary of the fit assessment, written in the persona's voice.",
    )
    constructive_feedback: str | None = Field(
        ...,
        description="Truly helpful, deep, and highly actionable professional advice on how the candidate can optimize their CV, highlight missing stacks, or self-study/obtain certifications to match this role in the future.",
    )


class FitAnalysisIn(BaseModel):
    job_id: UUID
    # Whose eyes judge the fit; "corporate" unless the user says the employer is a startup
    # or a research lab.
    company_type: CompanyType = "corporate"


class FitAnalysisOut(BaseModel):
    id: UUID
    job_id: UUID
    candidate_id: UUID
    company_type: CompanyType
    score: int
    verdict: Recommendation
    data: FitCheck
    model: str
    prompt_version: str
    created_at: datetime
