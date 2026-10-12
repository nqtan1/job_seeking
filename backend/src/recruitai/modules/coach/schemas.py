"""Coach DTOs (ADR 0016). A conversation is persisted org-scoped data; every turn sends the
stored history to the model explicitly (the gateway itself keeps no memory)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Role = Literal["user", "assistant"]
MAX_MESSAGE_CHARS = 4000


class ConversationIn(BaseModel):
    job_id: UUID | None = Field(
        None,
        description="A job from the inbox to discuss. Optional: general career advice.",
    )


class ConversationPatch(BaseModel):
    job_id: UUID | None = Field(
        description="The job to focus on (replaces the current one), or null to detach."
    )


class MessageIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)


class FocusJob(BaseModel):
    job_id: UUID
    title: str | None
    company: str | None


class Citation(BaseModel):
    title: str
    uri: str
    domain: str | None = None


class StepMeta(BaseModel):
    tool: str
    status: Literal["done", "error"]
    ms: int


class JobRef(BaseModel):
    job_id: UUID
    content_hash: str = Field(description="sha256 of the job data used for this reply.")


class MessageMeta(BaseModel):
    """What an assistant reply was grounded in (stored with the message, ``schema_version`` 1)."""

    schema_version: Literal[1] = 1
    prompt_version: str
    model: str
    job_ref: JobRef | None = None
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="What the prompt held: lengths and truncation flags of job, profile, fit, history.",
    )
    steps: list[StepMeta] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    search_suggestions_html: str | None = Field(
        default=None,
        description="Google Search Suggestion markup; render unmodified in a sandboxed iframe.",
    )
    degraded: list[str] = Field(
        default_factory=list,
        description="Notice codes: web_unavailable, step_limit, turn_timeout, tool_error.",
    )


class MessageOut(BaseModel):
    id: UUID
    role: Role
    content: str
    created_at: datetime
    meta: MessageMeta | None = None


class ConversationSummary(BaseModel):
    id: UUID
    job_id: UUID | None
    title: str | None = Field(
        description="The first message, clipped; null if none was sent."
    )
    updated_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    candidate_id: UUID
    job_id: UUID | None
    started_at: datetime
    focus: FocusJob | None = None
