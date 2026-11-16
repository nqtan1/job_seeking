"""The tool registry (ADR 0039): the one place that says what each tool is.

A tool is a row here (what it takes, what it gives back, what it costs, which rules apply) plus the
handler its module registers with it. Flows, agents and the web read this registry, so adding a tool
cannot leave one of them behind. Each module registers its own tools at import time. No dependency
on any feature module."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import AppError

# outside = leaves the app (e-mail, message)
Effect = Literal["read", "write", "outside"]
Ports = tuple[tuple[str, bool], ...]  # (input name, required)


@dataclass(frozen=True)
class Call:
    """What a tool's handler gets, whoever calls it (a flow step, an agent in chat). Values are the
    tool's inputs as text; the answer is its outputs as text."""

    db: AsyncSession
    llm: Any  # ai.gateway.LLMGateway (core does not import ai)
    org_id: UUID
    user_id: UUID | None
    job_id: UUID | None  # the job the run or the chat is about, if any
    values: dict[str, str]

    def get(self, name: str, default: str = "") -> str:
        return self.values.get(name, default)


Handler = Callable[
    [Any], Awaitable[dict[str, str]]
]  # takes a Call (or a flow step's Ctx, a Call)


def one_line(value: str | None) -> str:
    """Text a tool hands on in one line (titles, names, places)."""
    return " ".join((value or "").split())


class ToolFailed(AppError):
    """A tool could not finish: fixed codes, never exception text."""

    status_code = 502
    code = "tool_failed"
    default_detail = "This step could not finish."


class NoJob(ToolFailed):
    code = "no_job"
    default_detail = "This step needs a job: pick one when you run it."


class Cap(NamedTuple):
    """Daily limits of a tool with an outside effect. ``once``: a resumed step does not repeat it."""

    user: int  # per user per day
    everyone: int | None = None  # all users together per day
    once: bool = True  # False: repeatable (counted, but a resumed step just runs again)


@dataclass(frozen=True)
class Tool:
    id: str  # stored in flow graphs: never rename one
    pack: str  # "career" | "web" | "messages" | "core"
    inputs: Ports
    outputs: tuple[str, ...]
    effect: Effect = "read"
    cap: Cap | None = None  # None: no outside effect worth a ledger row
    ai_uses: int = 0  # model calls one step can make (the daily AI quota)
    needs_job: bool = False  # the run must be given a job
    starts_runs: bool = False  # starts other runs: allowed one level deep only
    pauses: bool = False  # parks the run until it is woken (the engine owns this state)
    chat: bool = False  # an agent may call it in chat
    page: str | None = None  # web route of its own screen
    untrusted: bool = (
        False  # its output is text written by outsiders (web pages, search results)
    )
    flag: str | None = (
        None  # name of the Settings bool that switches its pack on; None: always on
    )


_TOOLS: dict[str, Tool] = {}
_HANDLERS: dict[str, Handler] = {}


def register(tool: Tool, handler: Handler | None) -> None:
    """At import time. ``handler`` None: the engine runs it itself (for_each, wait)."""
    if tool.id in _TOOLS:
        raise RuntimeError(f"tool {tool.id} is registered twice")
    _TOOLS[tool.id] = tool
    if handler is not None:
        _HANDLERS[tool.id] = handler


def get(id: str) -> Tool:
    return _TOOLS[id]


def all() -> dict[str, Tool]:
    return dict(_TOOLS)


def handler(id: str) -> Handler:
    """KeyError for a tool the engine runs itself, or no tool at all."""
    return _HANDLERS[id]
