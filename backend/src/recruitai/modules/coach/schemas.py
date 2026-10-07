"""Coach DTOs (ADR 0016). A conversation is persisted org-scoped data; every turn sends the
stored history to the model explicitly (the gateway itself keeps no memory)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Role = Literal["user", "assistant"]
MAX_MESSAGE_CHARS = 4000


class ConversationIn(BaseModel):
    job_id: UUID | None = Field(
        None,
        description="A job from the inbox to discuss. Optional: general career advice.",
    )


class MessageIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)


class MessageOut(BaseModel):
    id: UUID
    role: Role
    content: str
    created_at: datetime


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
