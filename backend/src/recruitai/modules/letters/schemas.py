"""Letter content as structured blocks (ARCHITECTURE.md §10.1), never raw LaTeX.

Two models on purpose: ``LetterDraft`` is the LLM output schema (the five blocks the model
writes, in writing order); ``LetterContent`` is the stored/rendered letter, which adds the
blocks code fills in from the profile and job (``header``, ``recipient``, ``signature``) so
the model can never invent contact details. Templates render ``LetterContent``; changing a
template never needs the model again.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

Kind = Literal["cover"]  # spontaneous, follow-up, thank-you are v2 (§10.2)
Language = Literal["fr", "en"]
Tone = Literal["professional", "warm", "confident", "academic", "formal"]
Length = Literal["short", "standard", "detailed"]
Template = Literal["classic", "modern", "compact", "lettre_fr"]
# The persona of the base prompt; same vocabulary as fit analyses.
CompanyType = Literal["corporate", "startup", "phd"]
BlockName = Literal["subject", "salutation", "opening", "body", "closing"]
AssistAction = Literal[
    "shorten", "more_formal", "more_concrete", "add_metric", "fix_grammar"
]


class LetterDraft(BaseModel):
    """What the model writes. Fields are in writing order (guided decoding fills them in
    this order), and every one is required."""

    subject: str = Field(
        ..., description="Short subject line for the application, e.g. the job title"
    )
    salutation: str = Field(
        ...,
        description="Opening salutation only, e.g. 'Madame, Monsieur,' or 'Dear Hiring Manager,'",
    )
    opening: str = Field(
        ..., description="First paragraph: who the candidate is and why this job"
    )
    body: list[str] = Field(
        ...,
        min_length=1,
        description="Body paragraphs, one string each, grounded only in the candidate profile",
    )
    closing: str = Field(
        ...,
        description="Closing phrase only, without the candidate's name (the signature is added by code)",
    )


class BlockText(BaseModel):
    """LLM output when one block is regenerated."""

    text: str = Field(..., description="The new text of the requested block only")


class Header(BaseModel):
    """Sender block, copied from the Master profile (never written by the model)."""

    name: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    date: str | None = None


class Recipient(BaseModel):
    """Taken from the job posting."""

    company: str | None = None
    contact_name: str | None = None
    address: str | None = None


class LetterContent(BaseModel):
    header: Header
    recipient: Recipient
    subject: str
    salutation: str
    opening: str
    body: list[str]
    closing: str
    signature: str


class LetterIn(BaseModel):
    job_id: UUID
    language: Language = "fr"
    tone: Tone = "professional"
    length: Length = "standard"
    company_type: CompanyType = "corporate"
    template: Template = "classic"


class BlockEditIn(BaseModel):
    text: str = Field(..., max_length=5000)
    index: int | None = Field(
        None, ge=0, description="Paragraph number, for the body only"
    )


class BlockRegenerateIn(BaseModel):
    index: int | None = Field(
        None, ge=0, description="Paragraph number, for the body only"
    )


class LetterOut(BaseModel):
    id: UUID
    job_id: UUID | None
    kind: Kind
    template: Template
    language: Language
    tone: Tone
    length: Length
    company_type: CompanyType
    status: Literal["draft", "final"]
    render_status: Literal["none", "queued", "done", "failed"]
    pdf_document_id: UUID | None
    pdf_filename: str
    content: LetterContent
    created_at: datetime
    updated_at: datetime


class VersionOut(BaseModel):
    n: int
    content: LetterContent
    created_at: datetime


class RenderAccepted(BaseModel):
    task_id: UUID
    status_url: str


class PdfLinkOut(BaseModel):
    download_url: str


class ExportOut(BaseModel):
    format: Literal["text", "email"]
    subject: str | None = Field(None, description="Email subject (email format only)")
    body: str


class UnsupportedClaim(BaseModel):
    """Something the letter says that the Master profile (and the job) do not back up."""

    term: str
    kind: Literal["skill", "number", "name"]
    sentence: str


class KeywordCoverage(BaseModel):
    covered: list[str]
    missing: list[str]
    ratio: float | None = Field(None, description="None when the job lists no keywords")


class LetterQuality(BaseModel):
    keyword_coverage: KeywordCoverage
    word_count: int
    target_words: int
    within_target: bool
    cliches: list[str]
    avg_sentence_words: float
    long_sentences: int
    repeated_words: dict[str, int]


class LetterCheck(BaseModel):
    unsupported_claims: list[UnsupportedClaim]
    quality: LetterQuality


class AssistIn(BaseModel):
    block: BlockName
    selection: str = Field(..., min_length=1, max_length=2000)
    action: AssistAction


class AssistOut(BaseModel):
    """A suggestion only: the letter is not changed. Apply it with the block-edit endpoint."""

    suggestion: str
