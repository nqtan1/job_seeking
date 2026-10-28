"""Letter content as structured blocks (ARCHITECTURE.md §10.1), never raw LaTeX.
``LetterDraft`` is the LLM output; ``LetterContent`` adds code-filled blocks (header, recipient,
signature) so the model cannot invent contact details."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from recruitai.core.language import Language
from recruitai.modules.documents.signature_spec import MAX_WIDTH_MM, MIN_WIDTH_MM

SCHEMA_VERSION = 1

Kind = Literal["cover"]  # spontaneous, follow-up, thank-you are v2 (§10.2)
Tone = Literal["professional", "warm", "confident", "academic", "formal"]
Length = Literal["short", "standard", "detailed"]
Template = Literal["classic", "modern", "compact", "lettre_fr"]
# The persona of the base prompt; same vocabulary as fit analyses.
CompanyType = Literal["corporate", "startup", "phd"]
BlockName = Literal["subject", "salutation", "opening", "body", "closing"]
# "ai": the model writes the whole letter. "own_words": the user writes it; we only give ideas.
Mode = Literal["ai", "own_words"]
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


class BodyIdea(BaseModel):
    """One suggested paragraph: which requirement of the job to answer, with which proof."""

    requirement: str = Field(
        ..., description="A requirement or mission of the job this paragraph can answer"
    )
    proof: str = Field(
        ...,
        description="The concrete evidence from the candidate profile to use (project, result, tool)",
    )
    angle: str = Field(
        ...,
        description="One short sentence on how to put it, never the paragraph itself",
    )


class LetterIdeasDraft(BaseModel):
    """LLM output for a letter the user writes themself: ideas, never finished text."""

    opening: list[str] = Field(
        ..., description="2 or 3 short ideas for a personal opening hook"
    )
    body: list[BodyIdea] = Field(
        ..., description="One idea per body paragraph to write, strongest first"
    )
    closing: list[str] = Field(
        ..., description="1 or 2 short ideas for the closing paragraph"
    )


class LetterIdeas(BaseModel):
    """Stored and returned with the letter. ``body`` lines up with the letter's body
    paragraphs; an entry is null where the paragraph already holds the user's own text."""

    opening: list[str]
    body: list[BodyIdea | None]
    closing: list[str]


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


class SignatureImage(BaseModel):
    """The user's signature picture, printed above the typed name. The picture itself is the
    org's one stored signature (documents module); the letter only keeps the wanted width."""

    width_mm: int = Field(ge=MIN_WIDTH_MM, le=MAX_WIDTH_MM)


class SignatureSettingIn(BaseModel):
    width_mm: int | None = Field(
        None, ge=MIN_WIDTH_MM, le=MAX_WIDTH_MM, description="None removes the image"
    )


class LetterContent(BaseModel):
    header: Header
    recipient: Recipient
    subject: str
    salutation: str
    opening: str
    body: list[str]
    closing: str
    signature: str
    signature_image: SignatureImage | None = None  # old stored letters have none


class MotivationQuestion(BaseModel):
    """One question that draws a specific, personal answer out of the candidate."""

    question: str = Field(
        ..., description="One or two short sentences, concrete to this job and profile"
    )
    hint: str = Field(
        ..., description="One short line on what kind of detail makes a good answer"
    )


class MotivationQuestions(BaseModel):
    questions: list[MotivationQuestion] = Field(
        ..., description="Exactly 3 questions: why this, their story, what next"
    )


class MotivationQuestionsIn(BaseModel):
    job_id: UUID
    # None = the account language (the router fills it in).
    language: Language | None = None


class MotivationQuestionsOut(BaseModel):
    questions: list[MotivationQuestion]


class Answer(BaseModel):
    """The candidate's answer to one of the questions above, in their own words."""

    question: str = Field(..., min_length=1, max_length=300)
    answer: str = Field(..., max_length=800)


class LetterIn(BaseModel):
    job_id: UUID
    # The candidate's own voice: which fit strengths to put forward (tapped from the fit
    # analysis) and, in their words, why this role / employer. Both optional.
    highlights: list[Annotated[str, Field(max_length=300)]] = Field(
        default_factory=list, max_length=5
    )
    motivation: str | None = Field(None, max_length=1500)
    # Answers to the guided questions: the personal heart of the letter.
    answers: list[Answer] = Field(default_factory=list, max_length=4)
    # None = the account language (the router fills it in).
    language: Language | None = None
    tone: Tone = "professional"
    length: Length = "standard"
    company_type: CompanyType = "corporate"
    template: Template = "classic"
    mode: Mode = "ai"


class BlockEditIn(BaseModel):
    text: str = Field(..., max_length=5000)
    index: int | None = Field(
        None, ge=0, description="Paragraph number, for the body only"
    )


class RecipientPatch(BaseModel):
    """Only the fields sent change; an empty or blank string clears the value."""

    company: str | None = Field(None, max_length=200)
    contact_name: str | None = Field(None, max_length=200)
    address: str | None = Field(None, max_length=300)


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
    ideas: LetterIdeas | None = None
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


class SpellItem(BaseModel):
    """One piece of text to check: a block key (``subject``, ``opening``, ``body.1``…)."""

    key: str = Field(
        ..., pattern=r"^(subject|salutation|opening|closing|body\.\d{1,2})$"
    )
    text: str = Field(..., min_length=1, max_length=5000)


class SpellcheckIn(BaseModel):
    items: list[SpellItem] = Field(..., min_length=1, max_length=12)

    @model_validator(mode="after")
    def _keys_are_unique_and_total_is_bounded(self) -> "SpellcheckIn":
        keys = [i.key for i in self.items]
        if len(set(keys)) != len(keys):
            raise ValueError("each key may appear once")
        # A whole letter is a few thousand characters; this is not a general text endpoint.
        if sum(len(i.text) for i in self.items) > 12_000:
            raise ValueError("too much text to check at once")
        return self


class RawSpellIssue(BaseModel):
    """LLM output: a proposal the code still has to verify against the text."""

    key: str = Field(..., description="The key of the paragraph the error is in")
    wrong: str = Field(
        ...,
        description="The faulty word or short phrase, copied EXACTLY as written in the text",
    )
    context: str = Field(
        ...,
        description="A fragment of 4 to 10 words from the text that contains `wrong`, copied EXACTLY, so the exact occurrence can be found",
    )
    right: str = Field(..., description="The corrected word or short phrase")
    reason: str = Field(
        ..., description="Very short explanation of the rule, in the letter's language"
    )


class SpellFindings(BaseModel):
    issues: list[RawSpellIssue] = Field(
        ..., description="Every spelling, grammar or punctuation error; empty if none"
    )


class SpellIssue(BaseModel):
    """A verified correction: ``text[start:end] == wrong`` for the text that was sent, with
    ``start``/``end`` in UTF-16 code units (JavaScript string indexes)."""

    key: str
    start: int
    end: int
    wrong: str
    right: str
    reason: str


class SpellcheckOut(BaseModel):
    checked: int
    issues: list[SpellIssue]


class AssistOut(BaseModel):
    """A suggestion only: the letter is not changed. Apply it with the block-edit endpoint."""

    suggestion: str
