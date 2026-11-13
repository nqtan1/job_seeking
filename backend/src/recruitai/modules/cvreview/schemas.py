"""CV review schemas: ``LlmReview`` is what the model returns, ``ReviewData`` is the stored
``cv_reviews.data``. Required-but-nullable fields: optional ones are skipped by the small model
under guided decoding. ``RunAccepted`` is not shared: it lives in ``modules/radar/schemas.py``."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
MAX_BLOCKS = 150
MAX_CHARS = 600

Track = Literal["backend", "frontend", "fullstack", "data", "devops", "ml", "mobile"]
Level = Literal["intern", "junior", "mid", "senior", "staff"]
Rating = Literal["good", "moderate", "poor"]


class Block(BaseModel):
    """One line of the CV: the anchor of a comment. Also the (validated) input of an edited CV."""

    id: str = Field(..., pattern=r"^b\d{1,3}$")
    kind: Literal["heading", "bullet", "text"]
    section: Literal[
        "header", "summary", "experience", "projects", "skills", "education", "other"
    ]
    text: str = Field(
        ..., max_length=MAX_CHARS, pattern=r"^[^\x00]*$"
    )  # NUL: not JSONB-safe


# Stored reviews are validated against these types on every read: only ever ADD criteria and new
# fields WITH defaults (a test loads a v1 row). Renaming or removing breaks old reviews.
Criterion = Literal[
    "impact.metric",
    "impact.outcome",
    "scope.ownership",
    "scope.level_fit",
    "stack.named",
    "projects.depth",
    "skills.evidence",
    "structure.format",
    "language.concise",
    "progression.growth",
    "credibility.links",
]  # fmt: skip  (== checks.CRITERIA, checked by a test)


class Quote(BaseModel):
    """A passage of the CV a comment rests on: ``quote`` is an exact substring of block ``block_id``."""

    block_id: str
    quote: str


class BlockComment(BaseModel):
    """Guided decoding fills fields in this order: the basis first, the rating last."""

    block_id: str = Field(..., description="Id of the reviewed block, e.g. b12.")
    criterion: Criterion = Field(
        ..., description="The rubric point this comment is based on."
    )
    citations: list[Quote] = Field(..., description="Exact quotes this comment rests on (empty if none).")  # fmt: skip
    why: str = Field(..., description="Concrete reason, naming what in the quotes meets or misses the criterion.")  # fmt: skip
    improve: str | None = Field(
        ..., description="How to improve it; null when rating is good."
    )
    rewrite: str | None = Field(..., description="Rewrite keeping the original facts, [X%] for missing numbers; null if none.")  # fmt: skip
    rating: Rating
    source: Literal["ai", "rule"] = Field("ai", description="Set by code: never fill.")


class Dimension(BaseModel):
    score: float
    weight: float
    reason: str | None = Field(
        default=None, description="Why this score (model-scored dimensions)."
    )
    block_ids: list[str] = Field(default_factory=list, description="Blocks this score is based on.")  # fmt: skip


class Strength(BaseModel):
    text: str
    block_id: str | None = Field(..., description="Block that shows it; null if none.")


class LlmSummary(BaseModel):
    strengths: list[Strength]
    top_fixes: list[str] = Field(..., description="Block ids, most important first.")


class LlmDimension(BaseModel):
    reason: str = Field(
        ..., description="Why this score, naming what in the CV supports it."
    )
    block_ids: list[str] = Field(..., description="Ids of the blocks it is based on.")
    score: int = Field(..., ge=0, le=100)


class LlmReview(BaseModel):
    """Field order matters: guided decoding fills in schema order, scores come last."""

    comments: list[BlockComment]
    summary: LlmSummary
    scope: LlmDimension
    stack: LlmDimension
    projects: LlmDimension
    progression: LlmDimension


class ReviewData(BaseModel):
    blocks: list[Block]
    comments: list[BlockComment]
    dimensions: dict[str, Dimension]
    summary: LlmSummary
    pages: int
    truncated: bool = (
        False  # the CV had more than MAX_BLOCKS lines: the rest is not reviewed
    )
    grounding_rate: float


def _unique_ids(blocks: list[Block]) -> list[Block]:
    if len({b.id for b in blocks}) != len(blocks):
        raise ValueError("block ids must be unique")
    return blocks


Blocks = Annotated[
    list[Block], Field(min_length=1, max_length=MAX_BLOCKS), AfterValidator(_unique_ids)
]


class CvReviewIn(BaseModel):
    """A document to review, or (re-evaluate) a parent review plus the edited blocks."""

    document_id: UUID | None = None
    parent_review_id: UUID | None = None
    blocks: Blocks | None = None
    track: Track
    level: Level

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.document_id is not None) == (self.parent_review_id is not None) or (
            (self.document_id is None) == (self.blocks is None)
        ):
            raise ValueError("send document_id, or parent_review_id with blocks")
        return self


class RecheckIn(BaseModel):
    blocks: Blocks
    track: Track
    level: Level


class CvReviewListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID | None
    parent_id: UUID | None
    track: str
    level: str
    score: int
    created_at: datetime


class CvReviewOut(CvReviewListItem):
    data: ReviewData
    schema_version: int
    model: str
    prompt_version: str


class RunAccepted(BaseModel):
    task_id: UUID
    status_url: str


class RecheckOut(BaseModel):
    signals: dict[str, list[str]] = Field(..., description="Rule tags per block id.")
    dimensions: dict[str, float]
    score: int


class PdfLine(BaseModel):
    """One printed line of a block in the original PDF; x, y, w, h are fractions of page ``p``
    (0-based, origin top-left); ``s..e`` is the span of the block text on this line."""

    p: int
    x: float
    y: float
    w: float
    h: float
    s: int
    e: int


class PdfLayoutOut(BaseModel):
    ratios: list[
        float
    ]  # page height / width, so the page can be laid out before its image loads
    boxes: dict[str, list[PdfLine]]  # block id -> lines; a block not found has no entry
