"""DTO of ``GET /tools`` (ADR 0039). Names and descriptions are not here: the web translates them."""

from pydantic import BaseModel

from recruitai.core.tools import Effect, Tool


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
        )
