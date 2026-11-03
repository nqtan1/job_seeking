"""Helper DTOs (ADR 0031). Every bound here is repeated by a DB CHECK or enforced again in the
service: the client is never trusted."""

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

NAME = r"^[a-z][a-z0-9_]{0,31}$"
# Names that would collide with pydantic attributes or with the <data> blocks a helper receives.
CONTEXT_NAMES = {"profile", "job", "fit"}
MAX_INPUTS = 6
MAX_FIELDS = 12
MAX_INPUT_CHARS = (
    20_000  # per run, all inputs together (also the hand-off cap, ADR 0031)
)
ContextSource = Literal["profile", "job", "fit"]
FieldName = Annotated[str, StringConstraints(pattern=NAME)]


def _check_name(name: str) -> str:
    if hasattr(BaseModel, name) or name.startswith("model_") or name in CONTEXT_NAMES:
        raise ValueError(f"'{name}' is a reserved name")
    return name


MAX_VERSIONS = 100  # versions are pinned by runs and flows, so they are never pruned


def _has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(k) or _has_nul(v) for k, v in value.items())
    if isinstance(value, list | tuple):
        return any(_has_nul(v) for v in value)
    return False


class Strict(BaseModel):
    """Base of every request model. Postgres text and JSONB cannot hold NUL, so a payload that
    carries one anywhere is refused at the edge (a 422) instead of failing on write (a 500)."""

    @model_validator(mode="before")
    @classmethod
    def _no_nul(cls, data: Any) -> Any:
        if _has_nul(data):
            raise ValueError("NUL characters are not allowed")
        return data


class Avatar(BaseModel):
    """Parameters only, never markup: the web renders them (no uploads, no SVG injection)."""

    seed: UUID
    body: int = Field(ge=0, le=7)
    palette: int = Field(ge=0, le=11)
    eyes: int = Field(ge=0, le=5)
    accessory: int = Field(ge=0, le=7)


class InputField(BaseModel):
    name: FieldName
    label: str = Field(min_length=1, max_length=60)
    required: bool = True

    @model_validator(mode="after")
    def _name(self) -> Self:
        _check_name(self.name)
        return self


class OutputField(BaseModel):
    name: FieldName
    type: Literal["text", "number", "boolean", "choice", "list"]
    options: list[Annotated[str, StringConstraints(min_length=1, max_length=40)]] = []

    @model_validator(mode="after")
    def _check(self) -> Self:
        _check_name(self.name)
        if self.type == "choice":
            if not 2 <= len(self.options) <= 8 or len(set(self.options)) != len(
                self.options
            ):
                raise ValueError("a choice needs 2 to 8 distinct options")
        elif self.options:
            raise ValueError("only a choice has options")
        return self


class OutputSpec(BaseModel):
    kind: Literal["text", "fields"]
    fields: list[OutputField] = []

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind == "text" and self.fields:
            raise ValueError("a text result has no fields")
        if self.kind == "fields":
            if not 1 <= len(self.fields) <= MAX_FIELDS:
                raise ValueError(f"1 to {MAX_FIELDS} fields")
            if len({f.name for f in self.fields}) != len(self.fields):
                raise ValueError("duplicate field names")
        return self


class VersionSpec(BaseModel):
    """What a version is: the part a user edits and a run pins."""

    instructions: str = Field(min_length=1, max_length=4000)
    model_tier: Literal["fast", "smart"] = "fast"
    inputs: list[InputField] = Field(default=[], max_length=MAX_INPUTS)
    context_sources: list[ContextSource] = []
    output: OutputSpec = OutputSpec(kind="text")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len({i.name for i in self.inputs}) != len(self.inputs):
            raise ValueError("duplicate input names")
        if len(set(self.context_sources)) != len(self.context_sources):
            raise ValueError("duplicate context sources")
        if not self.instructions.strip():
            raise ValueError("instructions are empty")
        return self


Note = Annotated[str, StringConstraints(max_length=200)]


class AgentCreate(Strict):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field("", max_length=200)
    avatar: Avatar | None = None  # None = derived from the new id
    spec: VersionSpec
    note: Note = ""

    @model_validator(mode="after")
    def _name(self) -> Self:
        if not self.name.strip():
            raise ValueError("name is empty")
        return self


class AgentPatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=80)
    description: str | None = Field(None, max_length=200)
    avatar: Avatar | None = None

    @model_validator(mode="after")
    def _name(self) -> Self:
        if self.name is not None and not self.name.strip():
            raise ValueError("name is empty")
        return self


class VersionCreate(Strict):
    based_on: int = Field(ge=1, description="The version the editor started from")
    spec: VersionSpec
    note: Note = ""


class AgentVersionOut(BaseModel):
    id: UUID
    agent_id: UUID
    version: int
    spec: VersionSpec
    note: str
    created_at: datetime


class AgentOut(BaseModel):
    id: UUID
    name: str
    description: str
    avatar: Avatar
    current_version: int
    archived: bool
    created_at: datetime
    updated_at: datetime


class AgentDetail(AgentOut):
    version_id: UUID  # the current version's id: what a flow node pins
    spec: VersionSpec


class TrialIn(Strict):
    """Runs a draft (unsaved) spec: the editor's Try-it panel. Nothing is stored."""

    spec: VersionSpec
    inputs: dict[FieldName, str] = Field(default_factory=dict)
    job_id: UUID | None = None

    @model_validator(mode="after")
    def _size(self) -> Self:
        if sum(len(v) for v in self.inputs.values()) > MAX_INPUT_CHARS:
            raise ValueError(f"inputs are limited to {MAX_INPUT_CHARS} characters")
        return self


class TrialOut(BaseModel):
    result: dict[str, Any]
    model: str
    latency_ms: int
