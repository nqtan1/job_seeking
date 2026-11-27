"""DTOs of ``/tools`` (ADR 0039, 0043). Names and descriptions are not here: the web translates them."""

from pydantic import BaseModel

from recruitai.core.tools import Effect, Tool
from recruitai.modules.agents.helpers.schemas import RunInputs


class ToolInput(BaseModel):
    name: str
    required: bool


class ToolOut(BaseModel):
    id: str
    pack: str
    inputs: list[ToolInput]
    outputs: list[str]
    effect: Effect
    ai_uses: int
    daily_cap: int | None
    needs_job: bool
    chat: bool
    page: str | None
    mcp: bool  # served by the tools service: the Tools page can try it

    @classmethod
    def of(cls, t: Tool) -> "ToolOut":
        return cls(
            id=t.id,
            pack=t.pack,
            inputs=[ToolInput(name=n, required=r) for n, r in t.inputs],
            outputs=list(t.outputs),
            effect=t.effect,
            ai_uses=t.ai_uses,
            daily_cap=t.cap.user if t.cap else None,
            needs_job=t.needs_job,
            chat=t.chat,
            page=t.page,
            mcp=t.mcp,
        )


class ToolTryIn(RunInputs):
    """One real run of a tool from the Tools page: what an agent would get back."""


class ToolTryOut(BaseModel):
    outputs: dict[str, str]
    latency_ms: int
    remote: bool  # ran on the tools service (False: in-process, local dev)


class ToolsStatusOut(BaseModel):
    """``served`` None: tools run in-process (no service configured)."""

    remote: bool
    ok: bool
    served: list[str] | None
    latency_ms: int
