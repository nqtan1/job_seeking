from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from cv.schema import CVInformation
from fit.schema import FitCheck
from jobs.schema import JobPosition


class HRCandidateInput(BaseModel):
    candidate_id: str = Field(..., description="Stable identifier for the candidate")
    candidate_cv: CVInformation = Field(..., description="Structured CV information")
    custom_context: Optional[str] = Field(None, description="Optional candidate-specific context")


class HRBatchRankingRequest(BaseModel):
    job_information: JobPosition
    company_type: Literal["startup", "phd", "corporation"]
    candidates: List[HRCandidateInput] = Field(default_factory=list, min_length=1)
    recruiter_attend: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Recruiter scoring conditions and required constraints",
    )
    custom_context: Optional[str] = Field(None, description="Additional context for the batch ranking")
    shortlist_size: int = Field(default=5, ge=1, le=50)


class RankedCandidate(BaseModel):
    candidate_id: str
    candidate_name: str
    rank_position: int
    fit_score: int
    shortlisted: bool = False
    fit_check: FitCheck


class HRBatchRankingResult(BaseModel):
    message: str
    tenant_id: str
    company_type: str
    job_title: str
    company: str
    total_candidates: int
    shortlisted_count: int
    summary: str
    ranked_candidates: List[RankedCandidate]
    result_folder: str
    ranking_path: str
    request_path: str
    generated_at: datetime


class HRJobSubmission(BaseModel):
    message: str
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    tenant_id: str
    job_type: str = "hr_batch_ranking"


class HRJobStatusResponse(BaseModel):
    job_id: str
    tenant_id: str
    job_type: str
    status: Literal["queued", "running", "completed", "failed"]
    submitted_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None