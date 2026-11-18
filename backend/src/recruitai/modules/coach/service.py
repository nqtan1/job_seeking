"""The career coach: a persisted, org-scoped conversation (ADR 0009/0016). Stateless at the model
layer; a turn is stored only once the reply is complete, so a failed one can just be resent."""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import (
    ChatEvent,
    LLMGateway,
    Source,
    TextDelta,
    ToolCall,
    ToolCalls,
    ToolCallTurn,
    ToolResult,
    ToolResultTurn,
    ToolSpec,
    Turn,
    UserTurn,
)
from recruitai.ai.prompts.coach import PROMPT_VERSION
from recruitai.config import Settings
from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.language import Language
from recruitai.core.tools import Tool
from recruitai.modules.candidates import service as candidates
from recruitai.modules.coach import actions, inbox, repository
from recruitai.modules.coach import tools as tools_module
from recruitai.modules.coach.context import (
    HISTORY_MAX_MESSAGES,
    Prompt,
    build_prompt,
    helper_spec,
    window,
)
from recruitai.modules.coach.models import Conversation, Message
from recruitai.modules.coach.schemas import (
    MAX_MESSAGE_CHARS,
    ActionOutcome,
    Citation,
    MessageMeta,
    MessageOut,
    ProposalMeta,
    Role,
    StepMeta,
)
from recruitai.modules.jobs import service as jobs

logger = logging.getLogger(__name__)


async def create_conversation(
    db: AsyncSession,
    *,
    org_id: UUID,
    job_id: UUID | None = None,
    agent_id: UUID | None = None,
    settings: Settings | None = None,
) -> Conversation:
    """``agent_id``: a helper to chat with (404 for another org's or an archived one, or when
    helpers are switched off: ``settings`` is then required)."""
    profile = await candidates.require_profile(db, org_id=org_id)
    if job_id is not None:  # 404 for another org's job
        await jobs.get_job(db, org_id=org_id, job_id=job_id)
    if agent_id is not None:
        await helper_spec(db, settings, org_id=org_id, agent_id=agent_id)
    conversation = await repository.create_conversation(
        db, org_id=org_id, candidate_id=profile.id, job_id=job_id, agent_id=agent_id
    )
    await db.commit()
    return conversation


async def _helper_off(
    db: AsyncSession, settings: Settings, *, org_id: UUID, conversation_id: UUID
) -> bool:
    """A helper chat whose helper was archived, deleted or switched off since: its cards no
    longer run (the turn's own check, at confirm)."""
    conversation = await repository.get_conversation(
        db, org_id=org_id, conversation_id=conversation_id
    )
    if conversation is None or conversation.agent_id is None:
        return False
    try:
        await helper_spec(db, settings, org_id=org_id, agent_id=conversation.agent_id)
    except NotFound:
        return True
    return False


async def decide_action(
    db: AsyncSession,
    llm: LLMGateway,
    settings: Settings,
    *,
    org_id: UUID,
    user_id: UUID,
    conversation_id: UUID,
    action_id: UUID,
    decision: Literal["confirm", "cancel"],
    language: Language,
) -> ActionOutcome:
    """Confirm (runs it, once) or cancel a proposed action (``actions.decide``)."""
    off = decision == "confirm" and await _helper_off(
        db, settings, org_id=org_id, conversation_id=conversation_id
    )
    return await actions.decide(
        db,
        llm,
        settings,
        org_id=org_id,
        user_id=user_id,
        conversation_id=conversation_id,
        action_id=action_id,
        decision=decision,
        language=language,
        helper_off=off,
    )


async def set_job(
    db: AsyncSession, *, org_id: UUID, conversation_id: UUID, job_id: UUID | None
) -> Conversation:
    """Attach, switch or detach the job in focus. 404 for another org's job."""
    conversation = await get_conversation(
        db, org_id=org_id, conversation_id=conversation_id
    )
    if job_id is not None:
        await jobs.get_job(db, org_id=org_id, job_id=job_id)
    await repository.set_job(
        db, org_id=org_id, conversation_id=conversation_id, job_id=job_id
    )
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def delete_conversation(
    db: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> None:
    await get_conversation(db, org_id=org_id, conversation_id=conversation_id)  # 404
    await repository.delete_conversation(
        db, org_id=org_id, conversation_id=conversation_id
    )
    await db.commit()


async def focus_job(
    db: AsyncSession, conversation: Conversation
) -> tuple[UUID, str | None, str | None] | None:
    """(id, title, company) of the job in focus; None when none, or it was deleted since."""
    if conversation.job_id is None:
        return None
    try:
        job = await jobs.get_job(
            db, org_id=conversation.org_id, job_id=conversation.job_id
        )
    except NotFound:
        return None
    company = job.data.get("company")
    name = company.get("name") if isinstance(company, dict) else None
    title = job.data.get("title")
    return (
        job.id,
        title if isinstance(title, str) else None,
        name if isinstance(name, str) else None,
    )


async def get_conversation(
    db: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> Conversation:
    conversation = await repository.get_conversation(
        db, org_id=org_id, conversation_id=conversation_id
    )
    if conversation is None:
        raise NotFound("Conversation not found.")
    return conversation


async def assistant_conversation(db: AsyncSession, *, org_id: UUID) -> Conversation:
    """The org's Assistant conversation (ADR 0042), created on first call."""
    conversation = await inbox.assistant_conversation(db, org_id=org_id)
    await db.commit()
    return conversation


async def list_conversations(
    db: AsyncSession, *, org_id: UUID, limit: int = 30, offset: int = 0
) -> list[tuple[Conversation, str | None, datetime]]:
    return await repository.list_conversations(
        db, org_id=org_id, limit=limit, offset=offset
    )


async def list_messages(
    db: AsyncSession,
    *,
    org_id: UUID,
    conversation_id: UUID,
    limit: int = 100,
    offset: int = 0,
    latest: bool = False,
) -> list[MessageOut]:
    """Each proposed card with its action's live state, so it shows what happened."""
    await get_conversation(db, org_id=org_id, conversation_id=conversation_id)
    messages = await repository.list_messages(
        db,
        org_id=org_id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        latest=latest,
    )
    states = await actions.states(db, org_id=org_id, conversation_id=conversation_id)
    return [_message_out(m, states) for m in messages]


def _message_out(m: Message, states: dict[UUID, actions.State]) -> MessageOut:
    meta = _meta(m.meta)
    for card in meta.actions if meta else []:
        if card.action_id in states:
            card.status, card.code, card.result = states[card.action_id]
    return MessageOut(
        id=m.id,
        role=cast(Role, m.role),  # the DB CHECK allows only user/assistant
        content=m.content,
        created_at=m.created_at,
        meta=meta,
    )


def _meta(raw: dict[str, Any] | None) -> MessageMeta | None:
    """An unreadable ``meta`` (another schema_version) must not break reading the history."""
    try:
        return MessageMeta.model_validate(raw) if raw else None
    except ValidationError:
        logger.warning("coach message meta not readable")
        return None


Event = tuple[str, dict[str, Any]]
TOOL_TIMEOUT_S = 25.0
MAX_CALLS_PER_ROUND = 4
MAX_WEB_SEARCHES_PER_TURN = 2  # each one is a metered, billed grounded call


def _is_5xx(exc: UpstreamUnavailable) -> bool:
    cause = exc.__cause__
    status = getattr(cause, "code", None) or getattr(cause, "status_code", None)
    return isinstance(status, int) and status >= 500


async def _converse(llm: LLMGateway, **kwargs: Any) -> AsyncGenerator[ChatEvent]:
    """One model call of the loop. A provider 5xx before its first event is tried once more
    (AP-01 spike: 2 of 15 calls failed so, transiently); once anything was yielded, never."""
    for retry in (False, True):
        yielded = False
        try:
            async with aclosing(llm.converse(**kwargs)) as events:
                async for event in events:
                    yielded = True
                    yield event
            return
        except UpstreamUnavailable as exc:
            if yielded or retry or not _is_5xx(exc):
                raise
            kwargs["continuation"] = True  # the turn was charged once already


@dataclass
class _TurnState:
    """What one coach turn gathers across its model rounds."""

    degraded: list[str]
    read_untrusted: bool  # outside text other than the job in focus (web, history...)
    texts: list[str] = field(default_factory=list)
    steps: list[StepMeta] = field(default_factory=list)
    sources: dict[str, Source] = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)
    suggestions: str | None = None
    started: bool = False
    searches: int = 0
    rounds: int = 0
    allow: bool = True
    pending: ToolCalls | None = None
    proposals: list[ProposalMeta] = field(default_factory=list)


async def stream_reply(
    db: AsyncSession,
    llm: LLMGateway,
    settings: Settings,
    *,
    org_id: UUID,
    conversation_id: UUID,
    content: str | None,
    replace_last: bool = False,
    language: Language = "en",
    user_id: UUID | None = None,
) -> AsyncGenerator[Event]:
    """The coach's turn as events ``(name, data)``. Bounded tool loop (ADR 0023). Refusals and the
    first model call's errors raise before the first event (problem+json). ``replace_last`` regenerates."""
    conversation, recent, replaced, content = await _turn_input(
        db,
        org_id=org_id,
        conversation_id=conversation_id,
        content=content,
        replace_last=replace_last,
    )
    history = window(recent)
    prompt = await build_prompt(
        db,
        conversation,
        history,
        len(recent) - len(history),
        content,
        language,
        settings,
    )
    tools, tool_ctx, web = _turn_tools(
        db, llm, settings, prompt, conversation, language, user_id=user_id
    )
    degraded: list[str] = []
    if settings.coach_job_focus and not web and prompt.job_attached:
        degraded.append("web_unavailable")  # said to the user, never a silent gap
    # outsiders' text reached the model (a job ad, web results earlier in the chat, a tool this
    # turn): what it proposes after that is marked untrusted on its card (``actions.propose``)
    read_untrusted = any(
        (t := tools_module.tool_of(s.get("tool", ""))) is not None and t.untrusted
        for m in history
        for s in (m.meta or {}).get("steps", [])
    )
    state = _TurnState(degraded=degraded, read_untrusted=read_untrusted)
    async with aclosing(
        _rounds(llm, settings, prompt, tools, tool_ctx, state)
    ) as events:
        async for event in events:
            yield event
    async with aclosing(
        _store_reply(
            db,
            llm,
            prompt,
            state,
            org_id=org_id,
            conversation_id=conversation_id,
            content=content,
            replaced=replaced,
        )
    ) as events:
        async for event in events:
            yield event


async def _turn_input(
    db: AsyncSession,
    *,
    org_id: UUID,
    conversation_id: UUID,
    content: str | None,
    replace_last: bool,
) -> tuple[Conversation, list[Message], list[Message], str]:
    """(conversation, recent messages, the pair being regenerated, the message), refused early."""
    conversation = await get_conversation(
        db, org_id=org_id, conversation_id=conversation_id
    )
    recent = await repository.recent_messages(
        db,
        org_id=org_id,
        conversation_id=conversation_id,
        limit=HISTORY_MAX_MESSAGES + 2,
    )
    replaced: list[Message] = []
    if replace_last:
        if len(recent) < 2 or [m.role for m in recent[-2:]] != ["user", "assistant"]:
            raise ValidationFailed("There is no reply to regenerate.")
        replaced = recent[-2:]
        recent = recent[:-2]
        content = replaced[0].content
    content = (content or "").strip()
    if not content or len(content) > MAX_MESSAGE_CHARS:
        raise ValidationFailed(
            f"A message must be 1 to {MAX_MESSAGE_CHARS} characters."
        )
    return conversation, recent, replaced, content


def _turn_tools(
    db: AsyncSession,
    llm: LLMGateway,
    settings: Settings,
    prompt: Prompt,
    conversation: Conversation,
    language: Language,
    *,
    user_id: UUID | None,
) -> tuple[list[ToolSpec], tools_module.ToolContext, bool]:
    """(tools offered this turn, their context, whether web grounding is available)."""
    caps = llm.capabilities(PROMPT_VERSION)
    web = caps.web_grounding
    tools = (
        tools_module.specs(
            prompt.tools,
            settings,
            job_attached=prompt.job_attached,
            function_calling=caps.function_calling,
            web=web,
        )
        if settings.coach_job_focus
        else []
    )
    tool_ctx = tools_module.ToolContext(
        db=db,
        llm=llm,
        org_id=conversation.org_id,
        user_id=user_id,
        job_id=prompt.job_id,
        profile=prompt.profile,
        feature=PROMPT_VERSION,
        conversation_id=conversation.id,
        job_title=prompt.job_title,
        language=language,
    )
    return tools, tool_ctx, web


async def _rounds(
    llm: LLMGateway,
    settings: Settings,
    prompt: Prompt,
    tools: list[ToolSpec],
    tool_ctx: tools_module.ToolContext,
    state: _TurnState,
) -> AsyncGenerator[Event]:
    """Model call, tool calls, model call... until the model answers without calling a tool."""
    turns: list[Turn] = [UserTurn(prompt.text)]
    deadline = time.monotonic() + settings.coach_turn_timeout_s
    while True:
        state.pending = None
        async with aclosing(_model_round(llm, prompt, turns, tools, state)) as events:
            async for event in events:
                yield event
        pending = state.pending
        # past the step limit or the deadline, calls are ignored even if a backend still sends them
        if pending is None or not state.allow:
            break
        state.rounds += 1
        results: list[ToolResult] = []
        async with aclosing(
            _run_calls(pending.calls, tools, tool_ctx, state, results)
        ) as events:
            async for event in events:
                yield event
        turns += [ToolCallTurn(pending.calls, pending.raw), ToolResultTurn(results)]
        if state.rounds >= settings.coach_max_steps:
            state.allow = False
            state.degraded.append("step_limit")
            yield "notice", {"code": "step_limit"}
        elif time.monotonic() > deadline:
            state.allow = False
            state.degraded.append("turn_timeout")
            yield "notice", {"code": "turn_timeout"}


async def _model_round(
    llm: LLMGateway,
    prompt: Prompt,
    turns: list[Turn],
    tools: list[ToolSpec],
    state: _TurnState,
) -> AsyncGenerator[Event]:
    """One model call: its text streamed out, its tool calls (if any) left in ``state.pending``."""
    # aclosing: if the client disconnects and this generator is closed, the gateway's stream
    # is closed *now* (it records the call's outcome in its ``finally``).
    async with aclosing(
        _converse(
            llm,
            system=prompt.system,
            turns=turns,
            tools=tools,
            feature=PROMPT_VERSION,
            model="smart",
            allow_tools=state.allow,
            continuation=state.rounds > 0,
        )
    ) as events:
        async for event in events:
            if not state.started:  # first model output: no refusal can happen any more
                state.started = True
                yield "context", prompt.counts
                for code in state.degraded:
                    yield "notice", {"code": code}
            if isinstance(event, TextDelta):
                state.texts.append(event.text)
                yield "token", {"text": event.text}
            elif isinstance(event, ToolCalls):
                state.pending = event


async def _run_calls(
    calls: list[ToolCall],
    tools: list[ToolSpec],
    tool_ctx: tools_module.ToolContext,
    state: _TurnState,
    results: list[ToolResult],
) -> AsyncGenerator[Event]:
    """Run one round's tool calls in order, each answered in ``results``, with step events."""
    for n, call in enumerate(calls):
        step_id = f"{state.rounds}.{n}"
        if n >= MAX_CALLS_PER_ROUND:  # every parallel call is answered, few are run
            results.append(ToolResult(call.name, {"error": "too_many_calls"}))
            continue
        label = tools_module.label_for(call.name, call.args)
        yield (
            "step",
            {"id": step_id, "tool": call.name, "label": label, "status": "running"},
        )
        t0 = time.monotonic()
        tool = tools_module.tool_of(call.name)
        # never the model's own text
        logged = tool.id if tool is not None else "unknown"
        try:
            run = await _run_tool(call, tool, label, tools, tool_ctx, state)
        except Exception as exc:  # noqa: BLE001  (a tool must never crash the chat)
            logger.warning(
                "coach tool failed",
                extra={"tool": logged, "error_type": type(exc).__name__},
            )
            run = tools_module.ToolRun({"error": "tool_failed"}, label, ok=False)
            state.degraded.append(
                "web_unavailable" if call.name == "web_research" else "tool_error"
            )
            yield "notice", {"code": state.degraded[-1]}
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("coach tool", extra={"tool": logged, "ms": ms, "ok": run.ok})
        state.steps.append(
            StepMeta(tool=call.name, status="done" if run.ok else "error", ms=ms)
        )
        yield (
            "step",
            {
                "id": step_id,
                "tool": call.name,
                "label": label,
                "status": "done" if run.ok else "error",
            },
        )
        if run.proposal is not None:
            yield (
                "proposal",
                run.proposal.model_dump(mode="json", exclude={"status", "code"}),
            )
        for source in run.sources:
            state.sources.setdefault(source.uri, source)
        state.queries.extend(q for q in run.queries if q not in state.queries)
        state.suggestions = run.suggestions_html or state.suggestions
        results.append(ToolResult(call.name, run.result))


async def _run_tool(
    call: ToolCall,
    tool: Tool | None,
    label: str,
    tools: list[ToolSpec],
    tool_ctx: tools_module.ToolContext,
    state: _TurnState,
) -> tools_module.ToolRun:
    """One tool call, unless it is unknown or over budget. A write, capped or AI-spending tool is
    only proposed: the user confirms its card (ADR 0042)."""
    if tool is None or call.name not in {t.name for t in tools}:
        return tools_module.ToolRun({"error": "unknown_tool"}, label, ok=False)
    if tools_module.proposed(tool):
        return await actions.propose(
            call,
            tool,
            label,
            tool_ctx,
            state.proposals,
            read_untrusted=state.read_untrusted,
        )
    if call.name == "web_research" and state.searches >= MAX_WEB_SEARCHES_PER_TURN:
        return tools_module.ToolRun(
            {
                "error": "research_limit",
                "hint": "Answer with what you found.",
            },
            label,
            ok=False,
        )
    state.searches += call.name == "web_research"
    # reading the job in focus again adds no new outsider (it is already in the prompt)
    state.read_untrusted |= tool.untrusted and tool.id != "job_lookup"
    return await asyncio.wait_for(
        tools_module.run(call.name, call.args, tool_ctx), TOOL_TIMEOUT_S
    )


async def _store_reply(
    db: AsyncSession,
    llm: LLMGateway,
    prompt: Prompt,
    state: _TurnState,
    *,
    org_id: UUID,
    conversation_id: UUID,
    content: str,
    replaced: list[Message],
) -> AsyncGenerator[Event]:
    """Citations and suggestions out, then the turn stored (only now: a failed one is resent)."""
    reply = "".join(state.texts).strip()
    if not reply:
        raise UpstreamUnavailable(
            "The AI provider returned an empty response.", code="ai_response_invalid"
        )
    sources = state.sources
    if sources:
        yield (
            "citations",
            {
                "items": [
                    {"title": s.title, "uri": s.uri, "domain": s.domain}
                    for s in sources.values()
                ]
            },
        )
    if state.suggestions:
        yield "suggestions", {"html": state.suggestions}
    meta = MessageMeta(
        prompt_version=PROMPT_VERSION,
        model=llm.model_name("smart", PROMPT_VERSION),
        job_ref=prompt.job_ref,
        context=prompt.counts,
        steps=state.steps,
        citations=[
            Citation(title=s.title, uri=s.uri, domain=s.domain)
            for s in sources.values()
        ],
        queries=state.queries,
        search_suggestions_html=state.suggestions,
        degraded=list(dict.fromkeys(state.degraded)),
        actions=state.proposals,
    )
    if replaced:
        await actions.drop_pending(db, org_id=org_id, metas=[m.meta for m in replaced])
        removed = await repository.delete_messages(
            db, org_id=org_id, message_ids=[m.id for m in replaced]
        )
        if removed != len(replaced):  # another regenerate got there first
            raise ValidationFailed("This reply was already regenerated.")
    stored = await repository.add_turn(
        db,
        org_id=org_id,
        conversation_id=conversation_id,
        user_text=content,
        assistant_text=reply,
        assistant_meta=meta.model_dump(mode="json"),
    )
    await db.commit()
    yield "done", {"message_id": str(stored[1].id)}


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, Any]]]:
    """Transcripts included: coach conversations are the user's data (ADR 0016)."""
    return {
        "coach_conversations": rows_as_dicts(
            await repository.all_conversations(db, org_id=org_id)
        ),
        "coach_messages": rows_as_dicts(
            await repository.all_messages(db, org_id=org_id)
        ),
        "coach_actions": rows_as_dicts(await repository.all_actions(db, org_id=org_id)),
    }
