"""Flow DTOs (ADR 0031). The graph model itself lives in ``graph.py``."""

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from recruitai.modules.agents.graph import Graph, MapEntry
from recruitai.modules.agents.schemas import MAX_INPUT_CHARS, FieldName, Note, Strict


class IssueOut(BaseModel):
    code: str
    message: str
    node_id: UUID | None = None
    edge_id: UUID | None = None
    severity: Literal["error", "warning"]


class FlowCreate(Strict):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field("", max_length=200)
    graph: Graph
    note: Note = ""

    @model_validator(mode="after")
    def _name(self) -> "FlowCreate":
        if not self.name.strip():
            raise ValueError("name is empty")
        return self


class FlowPatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=80)
    description: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def _name(self) -> "FlowPatch":
        if self.name is not None and not self.name.strip():
            raise ValueError("name is empty")
        return self


class FlowVersionCreate(Strict):
    based_on: int = Field(ge=1)
    graph: Graph
    note: Note = ""


class FlowOut(BaseModel):
    id: UUID
    name: str
    description: str
    current_version: int
    archived: bool
    max_ai_calls: int
    created_at: datetime
    updated_at: datetime


class FlowDetail(FlowOut):
    graph: Graph
    issues: list[IssueOut]


class FlowVersionOut(BaseModel):
    id: UUID
    flow_id: UUID
    version: int
    graph: Graph
    note: str
    created_at: datetime


class ValidateIn(Strict):
    graph: Graph


class ValidateOut(BaseModel):
    issues: list[IssueOut]
    max_ai_calls: int
    ok: bool


class PreviewIn(Strict):
    """The editor's live preview of one hand-off: the same ``render_map`` the engine uses."""

    map: list[MapEntry] = Field(max_length=10)
    outputs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _size(self) -> "PreviewIn":
        if len(json.dumps(self.outputs, default=str)) > 4 * MAX_INPUT_CHARS:
            raise ValueError("the sample values are too large")
        return self


class PreviewValue(BaseModel):
    text: str
    chars: int


class PreviewOut(BaseModel):
    values: dict[str, PreviewValue]
    truncated: bool


class RunIn(Strict):
    inputs: dict[FieldName, str] = Field(default_factory=dict)
    job_id: UUID | None = None

    @model_validator(mode="after")
    def _size(self) -> "RunIn":
        if sum(len(v) for v in self.inputs.values()) > MAX_INPUT_CHARS:
            raise ValueError(f"inputs are limited to {MAX_INPUT_CHARS} characters")
        return self


class StepOut(BaseModel):
    node_id: UUID
    position: int
    status: Literal["pending", "running", "waiting", "done", "failed", "skipped"]
    output: dict[str, Any] | None
    error_code: str | None
    model: str | None
    latency_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None


class HandoffOut(BaseModel):
    edge_id: UUID
    from_node: UUID
    to_node: UUID
    payload: dict[str, Any]
    truncated: bool


class RunSummary(BaseModel):
    id: UUID
    flow_id: UUID
    flow_version_id: UUID
    trigger: Literal["manual", "schedule", "flow"]
    parent_run_id: UUID | None
    status: Literal["queued", "running", "waiting", "done", "failed", "cancelled"]
    error_code: str | None
    wake_at: datetime | None
    created_at: datetime
    finished_at: datetime | None


class RunOut(RunSummary):
    inputs: dict[str, Any]
    job_id: UUID | None
    result: dict[str, Any] | None
    started_at: datetime | None
    steps: list[StepOut]
    handoffs: list[HandoffOut]


class RunListItem(RunSummary):
    """One row of the "all runs" page."""

    flow_name: str


Cadence = Literal["hourly", "daily", "weekly"]


class ScheduleIn(Strict):
    """Run a flow on its own. Times are local to ``timezone`` (an IANA name such as Europe/Paris)."""

    cadence: Cadence
    at_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekday: int | None = Field(None, ge=0, le=6, description="0 = Monday")
    timezone: str = Field(min_length=1, max_length=64)
    inputs: dict[FieldName, str] = Field(default_factory=dict)
    job_id: UUID | None = None

    @model_validator(mode="after")
    def _shape(self) -> "ScheduleIn":
        if self.cadence != "hourly" and self.at_time is None:
            raise ValueError("a daily or weekly schedule needs a time")
        if self.cadence == "weekly" and self.weekday is None:
            raise ValueError("a weekly schedule needs a day")
        if self.cadence == "hourly" and (self.at_time or self.weekday is not None):
            raise ValueError("an hourly schedule has no time or day")
        if self.cadence == "daily" and self.weekday is not None:
            raise ValueError("a daily schedule has no day")
        if sum(len(v) for v in self.inputs.values()) > MAX_INPUT_CHARS:
            raise ValueError(f"inputs are limited to {MAX_INPUT_CHARS} characters")
        return self


class SchedulePatch(Strict):
    enabled: bool


class ScheduleOut(BaseModel):
    id: UUID
    flow_id: UUID
    cadence: Cadence
    at_time: str | None
    weekday: int | None
    timezone: str
    inputs: dict[str, Any]
    job_id: UUID | None
    enabled: bool
    paused_reason: Literal["failures", "inactive"] | None
    next_run_at: datetime
    last_run_at: datetime | None
