"""Coach DTOs (ADR 0016). A conversation is persisted org-scoped data; every turn sends the
stored history to the model explicitly (the gateway itself keeps no memory)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from recruitai.core.inbox import Kind

Role = Literal["user", "assistant"]
ConversationKind = Literal["chat", "assistant"]
MAX_MESSAGE_CHARS = 4000


class ConversationIn(BaseModel):
    job_id: UUID | None = Field(
        None,
        description="A job from the inbox to discuss. Optional: general career advice.",
    )
    agent_id: UUID | None = Field(
        None, description="A helper to chat with. Optional: null is the default coach."
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


ActionStatus = Literal["pending", "done", "cancelled", "failed", "expired"]


class ProposalMeta(BaseModel):
    """A card the reply proposed (ADR 0042). The SSE ``proposal`` event carries the same fields
    except ``status`` and ``code``. In ``GET .../messages`` both are read live from the action, so
    a card re-renders with its current state after a reload (pending older than 15 min: expired).
    ``summary`` is built by the server from ``args``; ``untrusted``: suggested after outside content
    (a web page, a job ad) was read."""

    action_id: UUID
    tool: str
    summary: str
    args: dict[str, str]
    untrusted: bool
    status: ActionStatus = "pending"
    code: str | None = None
    # GET only, once done: the ids the run produced (``run_id``, ``flow_id``...), for links
    result: dict[str, str] | None = None


class InboxMeta(BaseModel):
    """An item the app posted to the Assistant conversation (ADR 0042): no model wrote it."""

    kind: Kind
    link: str | None = Field(
        None, description="An app path, e.g. /automations/runs/{id}."
    )


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
    actions: list[ProposalMeta] = Field(
        default_factory=list,
        description="Actions this reply proposed; confirm or cancel with POST .../actions/{action_id}.",
    )
    inbox: InboxMeta | None = None


class MessageOut(BaseModel):
    id: UUID
    role: Role
    content: str
    created_at: datetime
    meta: MessageMeta | None = None


class ConversationSummary(BaseModel):
    id: UUID
    job_id: UUID | None
    kind: ConversationKind = Field(
        "chat",
        description="'assistant': the inbox conversation (GET /coach/assistant).",
    )
    title: str | None = Field(
        description="The first message, clipped; null if none was sent."
    )
    updated_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    candidate_id: UUID
    job_id: UUID | None
    agent_id: UUID | None
    kind: ConversationKind = "chat"
    started_at: datetime
    focus: FocusJob | None = None


class ActionDecision(BaseModel):
    decision: Literal["confirm", "cancel"]


class ActionOutcome(BaseModel):
    """``done``: ``result`` holds the ids the run produced (``run_id``, ``flow_id``...), if any.
    ``failed``: ``code`` says why (``tool_off``, ``cap_reached``, ``memory_full``, ``no_job``,
    ``tool_failed``...)."""

    status: Literal["done", "cancelled", "failed"]
    result: dict[str, str] | None = None
    code: str | None = None
