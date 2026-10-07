"""Application tracker DTOs. Moved from the legacy ``domain/applications/schema.py`` with the
status set kept as is (``to_apply, applied, in_review, interview, offer, rejected, ghosted``).

Not ported: the legacy ``cv_file`` / ``cover_letter_file`` / ``special_documents`` fields (they
held client-supplied file paths, a path-traversal hole: files go through ``documents`` ids) and
the document-prep timestamps. Added: ``job_title`` (an application without a linked job still
needs a role), ``next_statuses`` (so a UI never offers an illegal move) and the event timeline.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Status = Literal[
    "to_apply", "applied", "in_review", "interview", "offer", "rejected", "ghosted"
]
Source = Literal[
    "linkedin", "indeed", "france_travail", "referral", "company_site", "other"
]

# Where an application may go from each status. `ghosted` means "no news": a late reply moves
# it back into the pipeline. `rejected` is final; an offer can still end as `rejected`
# (declined or withdrawn). Staying in the same status is not a move.
TRANSITIONS: dict[Status, tuple[Status, ...]] = {
    "to_apply": ("applied",),
    "applied": ("in_review", "interview", "offer", "rejected", "ghosted"),
    "in_review": ("interview", "offer", "rejected", "ghosted"),
    "interview": ("offer", "rejected", "ghosted"),
    "ghosted": ("in_review", "interview", "offer", "rejected"),
    "offer": ("rejected",),
    "rejected": (),
}


def next_statuses(status: str) -> list[Status]:
    return list(TRANSITIONS[status])  # type: ignore[index]  # callers pass DB-checked values


class ApplicationIn(BaseModel):
    job_id: UUID | None = Field(
        None, description="A job from the inbox; fills company and title"
    )
    company_name: str | None = Field(None, min_length=1, max_length=200)
    job_title: str | None = Field(None, max_length=200)
    source: Source = "other"
    status: Literal["to_apply", "applied"] = "to_apply"
    applied_at: date | None = None
    notes: str | None = Field(None, max_length=5000)

    @model_validator(mode="after")
    def _company_needed_without_a_job(self) -> "ApplicationIn":
        if self.job_id is None and not self.company_name:
            raise ValueError("company_name is required when no job is linked")
        return self


class ApplicationUpdate(BaseModel):
    """PATCH: only the fields sent change. Status is not here: it moves through
    ``POST .../status`` so every change leaves an event."""

    company_name: str | None = Field(None, min_length=1, max_length=200)
    job_title: str | None = Field(None, max_length=200)
    source: Source | None = None
    applied_at: date | None = None
    notes: str | None = Field(None, max_length=5000)
    interview_at: datetime | None = None
    contact: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def _required_fields_cannot_be_nulled(self) -> "ApplicationUpdate":
        for name in ("company_name", "source"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class StatusChangeIn(BaseModel):
    status: Status
    note: str | None = Field(None, max_length=1000)


class ApplicationOut(BaseModel):
    id: UUID
    job_id: UUID | None
    company_name: str
    job_title: str | None
    source: Source
    status: Status
    next_statuses: list[Status]
    applied_at: date | None
    notes: str | None
    interview_at: datetime | None
    contact: str | None
    created_at: datetime
    updated_at: datetime


class EventOut(BaseModel):
    id: UUID
    from_status: Status | None
    to_status: Status
    at: datetime
    note: str | None


class ApplicationDocumentIn(BaseModel):
    document_id: UUID


class ApplicationDocumentOut(BaseModel):
    document_id: UUID
    kind: str
    mime: str
    size: int
    created_at: datetime
    filename: str
    download_url: str
    save_url: str
