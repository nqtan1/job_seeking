from typing import Dict, List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field

from cv.schema import CVInformation
from jobs.schema import JobPosition


class Recommendation(str, Enum):
    GO = "go"
    MAYBE = "maybe"
    NO_GO = "no_go"


class FitCheck(BaseModel):
    """
    Structured fit assessment between a candidate's CV and a job description,
    evaluated through a persona-specific lens (corporate / PhD / startup).
    """

    is_fit: bool = Field(
        ...,
        description="Overall boolean verdict: True if the candidate is a viable fit for this role, False otherwise."
    )

    fit_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Overall fit score from 0 to 100, calibrated to the specific persona's evaluation logic (corporate/PhD/startup criteria differ)."
    )

    recommendation: Recommendation = Field(
        ...,
        description="Final hiring recommendation: 'go', 'maybe', or 'no_go', matching the reasoning a real recruiter in this persona would give."
    )

    strengths: List[str] = Field(
        ...,
        description="Concrete strengths of the candidate relative to this job, framed using the persona's focus areas and vocabulary."
    )

    gaps: List[str] = Field(
        ...,
        description="Concrete gaps, risks, or red flags identified, framed the way this persona would flag them (e.g. seniority mismatch, topic misalignment, lack of ownership evidence)."
    )

    reasons: List[str] = Field(
        ...,
        description="List of reasons supporting the overall verdict — combines both why the candidate fits and why they might not, in priority order."
    )

    key_missing_requirements: Optional[List[str]] = Field(
        default=None,
        description="Specific hard requirements from the job description that the candidate does not appear to meet (e.g. missing certification, required years of experience, specific tool/language)."
    )

    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model's confidence in this assessment (0.0-1.0), lower if the CV or job description had missing/ambiguous information."
    )

    summary: Optional[str] = Field(
        default=None,
        description="1-3 sentence executive summary of the fit assessment, written in the persona's voice."
    )


class FitAnalysisRequest(BaseModel):
    candidate_cv: CVInformation
    job_information: JobPosition
    company_type: Literal["startup", "phd", "corporation"]
    recruiter_attend: Optional[Dict] = Field(default=None, description="Recruiter preferences or custom scoring criteria")
    custom_context: Optional[str] = Field(default=None, description="Optional free-form context for the fit analysis")


class FitAnalysisResponse(BaseModel):
    message: str
    company_type: str
    fit_check: FitCheck
    result_folder: str
    analysis_path: str
    request_path: str