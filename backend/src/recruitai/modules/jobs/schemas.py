"""``JobPosition`` is the LLM output schema for job extraction and the stored
``job_postings.data``. Moved from the legacy ``domain/jobs/analysis/schema.py`` (extraction
part only: the candidate/recruiter analysis models are not ported) and
``domain/jobs/search/schema.py``.

Sources are manual text, an uploaded file, or France Travail. Pasting a URL to auto-fetch is
v2 (D5), so no input model has a URL field.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

JobSource = Literal["manual", "file", "france_travail"]


class CompanyInfo(BaseModel):
    name: str
    type: Literal["employer", "cabinet_recrutement", "esn"] | None = Field(
        default=None, description="Employer, recruiting agency, or ESN"
    )
    logo_url: str | None = None


class Badges(BaseModel):
    contract_type: str | None = None
    location: str | None = Field(
        default=None, description="Short form location, e.g. Paris 1er"
    )
    location_full: str | None = Field(
        default=None,
        description="Full form location, e.g. 75 - Paris 1er Arrondissement",
    )
    remote_policy: str | None = None
    experience_level: str | None = None
    salary: str | None = Field(default=None, description="e.g. 40k-50k EUR/year")


class AboutCompany(BaseModel):
    summary: str | None = None
    truncate_at_chars: int = 180


class Profile(BaseModel):
    experience: str | None = Field(...)
    education: str | None = Field(...)
    technical_skills: list[str]
    soft_skills: list[str]
    nice_to_have: list[str]


class Modalities(BaseModel):
    location_detail: str | None = None
    start_date: str | None = None
    duration: str | None = None


class SourceMeta(BaseModel):
    industry: str | None = None
    raw_description_hash: str | None = None


class CompensationInfo(BaseModel):
    """Salary and benefits information"""

    min_salary: float | None = Field(default=None, description="Minimum salary in EUR")
    max_salary: float | None = Field(default=None, description="Maximum salary in EUR")
    salary_currency: str | None = Field(default="EUR", description="Currency")
    salary_frequency: str | None = Field(
        default=None, description="Annual, Monthly, etc."
    )
    benefits: list[str] | None = Field(
        default=None, description="Benefits: health insurance, bonus, RTT, etc."
    )
    variable_portion: str | None = Field(
        default=None, description="Bonus, commissions, or 'part variable'"
    )
    has_13th_month: bool = Field(default=False, description="Is there a 13ème mois?")
    rtt_days: int | None = Field(
        default=None, description="Number of RTT days per year"
    )
    meal_vouchers: bool | None = Field(
        default=None, description="Tickets Restaurant / Swile"
    )


class JobPosition(BaseModel):
    """Structured information for a job position.

    Lists and the ``badges``/``profile`` fields are required (nullable where a value may be
    absent), unlike the legacy defaults: with optional fields the small self-hosted model
    returned an empty skeleton under guided decoding (measured, same as ``CVInformation``).
    """

    job_id: str | None = None
    title: str = Field(
        ..., description="Job position title, preserving (H/F) if present"
    )
    company: CompanyInfo
    badges: Badges
    about_company: AboutCompany
    missions: list[str] = Field(
        ..., description="Array of individual mission bullets, full sentences"
    )
    tech_stack: list[str] = Field(
        ..., description="Short tags/keywords only, no sentences"
    )
    working_methods: list[str] = Field(
        ..., description="e.g. Agile, Travail collaboratif"
    )
    profile: Profile
    modalities: Modalities
    compensation: CompensationInfo | None = None
    source_meta: SourceMeta
    job_description_text: str | None = Field(
        default=None, description="The full, raw job description text"
    )


class UnifiedJobSearchResult(BaseModel):
    """Standardized, post-processed job search result across providers."""

    id: str = Field(..., description="Unique job listing ID from the provider")
    title: str = Field(..., description="Job position title")
    company: str | None = Field(default=None, description="Company/Employer name")
    location: str | None = Field(
        default=None, description="Job location (city, department, region)"
    )
    date: str | None = Field(
        default=None, description="Publication date in YYYY-MM-DD format"
    )
    url: str = Field(..., description="Full original URL to view or apply for the job")
    work_mode: str | None = Field(
        default=None, description="Remote, hybrid, or on-site policy"
    )
    regions: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    skills: list[str] = Field(
        default_factory=list, description="Key skills extracted from listing"
    )
    description: str | None = Field(
        default=None, description="Full or excerpt description"
    )
    contract_type: str | None = Field(
        default=None, description="Short code (e.g. CDI, CDD, Freelance)"
    )
    contract_type_label: str | None = Field(
        default=None, description="Human-readable contract type name"
    )
    experience_label: str | None = Field(
        default=None, description="Required experience description"
    )
    salary_label: str | None = Field(
        default=None, description="Human-readable salary statement"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Platform-specific custom metadata"
    )


class UnifiedJobSearchResponse(BaseModel):
    meta: dict[str, Any] = Field(
        ..., description="Pagination metadata: count, page, total results"
    )
    results: list[UnifiedJobSearchResult]


class ManualJobIn(BaseModel):
    source: Literal["manual"]
    text: str = Field(..., min_length=1, max_length=30_000)


class FileJobIn(BaseModel):
    source: Literal["file"]
    document_id: UUID


class SearchJobIn(BaseModel):
    """Save one France Travail search result to the inbox."""

    source: Literal["france_travail"]
    external_id: str = Field(..., min_length=1, max_length=100)


# The only ways a job enters the inbox (D5: no URL source in v1).
JobIn = Annotated[ManualJobIn | FileJobIn | SearchJobIn, Field(discriminator="source")]


class JobOut(BaseModel):
    id: UUID
    source: JobSource
    external_id: str | None
    data: JobPosition
    schema_version: int
    created_at: datetime
