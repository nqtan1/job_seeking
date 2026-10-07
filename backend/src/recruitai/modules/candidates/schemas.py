"""``CVInformation`` is both the LLM output schema and the stored ``candidate_profiles.data``.

Moved from the legacy ``domain/cv/schema.py`` (phase 1 only; the recruiter-analysis models
are not ported, ``hr`` is out of v1). Minimization (ARCHITECTURE.md §11.3): there is
deliberately no photo, date of birth, gender, nationality or marital-status field, so the
model cannot return them and the profile cannot store them.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = 1


# Emails are plain ``str`` (legacy: ``EmailStr``): vLLM guided decoding rejects the JSON-schema
# ``format: email`` ("not supported by Outlines"), and a malformed address on a CV should not
# fail the whole extraction.
class PersonalInfo(BaseModel):
    """Raw personal information extracted from CV"""

    name: str = Field(..., description="Full name")
    email: str | None = Field(None, description="Email address")
    # Optional (legacy: required): a required field forces the model to invent a number
    # when the CV has none, which the prompt forbids.
    phone: str | None = Field(None, description="Phone number")
    address: str | None = Field(None, description="Physical address")
    linkedin: str | None = Field(None, description="LinkedIn profile url")
    github: str | None = Field(None, description="Github profile url")
    website: str | None = Field(None, description="Personal website/portfolio")


class Reference(BaseModel):
    """Reference information from the CV"""

    name: str = Field(..., description="Name of the reference")
    title: str | None = Field(None, description="Title or position of the reference")
    company: str | None = Field(None, description="Company of the reference")
    email: str | None = Field(None, description="Email address of the reference")
    phone: str | None = Field(None, description="Phone number of the reference")
    relationship: str | None = Field(
        None, description="Relationship to the candidate (e.g., Professor, Manager)"
    )


class Formation(BaseModel):
    """Raw educational history"""

    degree: str = Field(..., description="Degree type (e.g., Bachelor, Master, PhD)")
    field: str = Field(..., description="Field of study")
    institution: str = Field(..., description="University/School name")
    gpa: float | None = Field(None, description="GPA score")
    subjects: list[str] | None = Field(None, description="Main subjects studied")
    description: str | None = Field(
        None, description="Additional context about education"
    )


class Experience(BaseModel):
    """Raw work history"""

    job_title: str = Field(..., description="Job position/title")
    company: str = Field(..., description="Company or Laboratory name")
    # Required-but-nullable: with an optional field the small self-hosted model always picked
    # null under guided decoding (measured), even when the CV states dates.
    start_date: str | None = Field(..., description="Start date as written in the CV")
    end_date: str | None = Field(..., description="End date as written, or 'Present'")
    location: str | None = Field(None, description="Work location")
    description: str | None = Field(
        None, description="Responsibilities and achievements"
    )
    skills_used: list[str] | None = Field(
        None, description="Technologies mentioned in this role"
    )


class RawSkill(BaseModel):
    """Raw skill mentioned by candidate"""

    name: str = Field(..., description="Skill name")
    category: str | None = Field(None, description="Technical, Soft, etc.")


class CVInformation(BaseModel):
    """Structured raw data extracted from a CV."""

    personal_info: PersonalInfo
    # Required (no default): with an optional list a small model skips the section entirely.
    formations: list[Formation]
    experiences: list[Experience]
    skills: list[RawSkill]
    summary: str | None = Field(
        None, description="Professional summary or cover letter text"
    )
    references: list[Reference] | None = Field(
        default_factory=list, description="Professional references"
    )


class ProfileOut(BaseModel):
    id: UUID
    document_id: UUID | None
    data: CVInformation
    schema_version: int
    updated_at: datetime


class ProfileUpdate(BaseModel):
    """PATCH body: each top-level section that is sent replaces that section whole;
    sections left out are untouched."""

    personal_info: PersonalInfo | None = None
    formations: list[Formation] | None = None
    experiences: list[Experience] | None = None
    skills: list[RawSkill] | None = None
    summary: str | None = None
    references: list[Reference] | None = None

    @model_validator(mode="after")
    def _required_sections_cannot_be_nulled(self) -> "ProfileUpdate":
        # Omit a section to keep it; null would erase one the profile requires.
        for name in ("personal_info", "formations", "experiences", "skills"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ExtractRequest(BaseModel):
    document_id: UUID
