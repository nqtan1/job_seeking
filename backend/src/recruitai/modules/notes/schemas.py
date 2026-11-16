"""Notes schemas. ``Summary`` is what the model returns for the ``summarise`` tool."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_BODY = 20000
_NO_NUL = r"^[^\x00]*$"  # not storable in Postgres text


class NoteIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, pattern=_NO_NUL)
    body: str = Field(..., min_length=1, max_length=MAX_BODY, pattern=_NO_NUL)
    # shown as a link: http(s) only, never javascript: or data:
    source_url: str | None = Field(None, max_length=2000, pattern=r"^https?://\S+$")


class NoteOut(NoteIn):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class Summary(BaseModel):
    summary: str = Field(..., description="The summary, a few sentences.")
    quotes: list[str] = Field(
        ..., description="Passages copied character-for-character from the text."
    )
