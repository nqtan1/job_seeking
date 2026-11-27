"""Proposed actions (ADR 0042). A chat tool that writes, has a daily cap or spends AI uses never runs
inside the turn: the turn stores a pending action and the web shows a card the server wrote. Only the
user's click (``decide``) runs the registry handler, once, with the tool's flag, the daily cap shared
with flows and the AI quota checked at that moment. The model never sees this path."""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway, ToolCall
from recruitai.config import Settings
from recruitai.core import tool_calls
from recruitai.core import tools as registry
from recruitai.core.errors import AppError, Conflict, NotFound
from recruitai.core.language import Language
from recruitai.core.tools import visible
from recruitai.modules.agents.flows import chat_tools
from recruitai.modules.agents.flows import service as flows
from recruitai.modules.applications.tools import tracker_args
from recruitai.modules.candidates import service as candidates
from recruitai.modules.coach import guard, repository
from recruitai.modules.coach.schemas import ActionOutcome, ActionStatus, ProposalMeta
from recruitai.modules.coach.tools import ToolContext, ToolRun, inputs

logger = logging.getLogger(__name__)

MAX_PER_TURN = 3
EXPIRES = timedelta(minutes=15)
ARG_CHARS = 4000  # one input, like one chat message
SHOWN_CHARS = 80  # one value in a summary; the free texts below are shown whole
SHOWN_WHOLE = frozenset({"text", "query"})  # a fact and a search: <= 200 once prepared
# tools whose meaning comes from the job the user put in focus: the job ad alone does not make
# their card untrusted (free-text tools stay flagged whenever the turn read outside text)
JOB_BOUND = frozenset({"add_to_tracker", "fit_check", "letter_draft"})


class ActionExpired(AppError):
    status_code = 410
    code = "action_expired"
    default_detail = "This action expired: ask for it again in the chat."


class ActionDecided(Conflict):
    code = "action_decided"
    default_detail = "This action was already confirmed or cancelled."


# What a card says, from the stored args only (never the model's prose).
_SUMMARY: dict[str, dict[Language, str]] = {
    "add_to_tracker": {
        "en": "Add {what} to your tracker",
        "fr": "Ajouter {what} à votre suivi",
        "vi": "Thêm {what} vào danh sách theo dõi",
    },
    "save_note": {
        "en": "Save a note: {title}",
        "fr": "Enregistrer une note : {title}",
        "vi": "Lưu ghi chú: {title}",
    },
    "letter_draft": {
        "en": "Draft a cover letter for {job}",
        "fr": "Rédiger une lettre de motivation pour {job}",
        "vi": "Soạn thư xin việc cho {job}",
    },
    "fit_check": {
        "en": "Check your fit with {job}",
        "fr": "Évaluer votre adéquation avec {job}",
        "vi": "Đánh giá mức phù hợp với {job}",
    },
    "find_offers": {
        "en": "Find new offers: {query}",
        "fr": "Chercher de nouvelles offres : {query}",
        "vi": "Tìm tin tuyển dụng mới: {query}",
    },
    "remember": {
        "en": "Remember: {text}",
        "fr": "Retenir : {text}",
        "vi": "Ghi nhớ: {text}",
    },
    "set_up_job_hunter": {
        "en": "Every day, find {query} and prepare the good ones",
        "fr": "Chaque jour, chercher {query} et préparer les bonnes offres",
        "vi": "Mỗi ngày, tìm {query} và chuẩn bị các tin phù hợp",
    },
    "run_routine": {
        "en": "Run {name} now",
        "fr": "Lancer {name} maintenant",
        "vi": "Chạy {name} ngay",
    },
}
_ANY: dict[Language, str] = {
    "en": "Run {tool}",
    "fr": "Lancer {tool}",
    "vi": "Chạy {tool}",
}
_THIS_JOB: dict[Language, str] = {
    "en": "this job",
    "fr": "cette offre",
    "vi": "công việc này",
}
_DONE: dict[Language, str] = {
    "en": "Done: {summary}.",
    "fr": "Fait : {summary}.",
    "vi": "Đã xong: {summary}.",
}


def clean_args(tool: registry.Tool, args: dict[str, Any]) -> dict[str, str] | None:
    """The tool's own inputs as trimmed, visible text (anything else dropped), or None when a
    required one is missing or a value is not text or too long."""
    out: dict[str, str] = {}
    for name, required in inputs(tool):
        value = args.get(name)
        if value is None and not required:
            continue
        if not isinstance(value, str) or len(value) > ARG_CHARS:
            return None
        value = visible(value).strip()  # no NUL (JSONB), no hidden characters
        if required and not value:
            return None
        if value:
            out[name] = value
    return out


def summary(
    tool_id: str, args: dict[str, str], job_title: str | None, language: Language
) -> str:
    fields = defaultdict(
        str,
        {
            k: registry.one_line(v)[: None if k in SHOWN_WHOLE else SHOWN_CHARS]
            for k, v in args.items()
        },
    )
    fields["what"] = " @ ".join(x for x in (fields["title"], fields["company"]) if x)
    fields["job"] = registry.one_line(job_title)[:SHOWN_CHARS] or _THIS_JOB[language]
    fields["tool"] = tool_id
    return _SUMMARY.get(tool_id, _ANY)[language].format_map(fields)[:300]


Prepared = dict[str, str] | str  # the args the handler will get, or a fixed code


async def _fact(ctx: ToolContext, args: dict[str, str]) -> Prepared:
    text = candidates.fact_text(args["text"])
    return {"text": text} if text else "invalid_arguments"


async def _hunter(ctx: ToolContext, args: dict[str, str]) -> Prepared:
    return chat_tools.hunter_args(args)


async def _routine(ctx: ToolContext, args: dict[str, str]) -> Prepared:
    try:
        return await chat_tools.routine_args(ctx.db, ctx.org_id, args)
    except AppError as exc:  # not found, ambiguous, sends messages
        return exc.code


async def _tracker(ctx: ToolContext, args: dict[str, str]) -> Prepared:
    return tracker_args(args)


# args turned into exactly what the handler will use, so the card shows what runs (PA-11)
_PREPARE: dict[str, Callable[[ToolContext, dict[str, str]], Awaitable[Prepared]]] = {
    "remember": _fact,
    "add_to_tracker": _tracker,
    "set_up_job_hunter": _hunter,
    "run_routine": _routine,
}


async def _prepare(
    ctx: ToolContext, tool: registry.Tool, args: dict[str, Any]
) -> Prepared:
    clean = clean_args(tool, args)
    if clean is None:
        return "invalid_arguments"
    if (prepare := _PREPARE.get(tool.id)) is not None:
        prepared = await prepare(ctx, clean)
        if isinstance(prepared, str):
            return prepared
        clean = prepared
    # a search leaves the app: never with the candidate's identity in it (as web_research)
    if "query" in clean and (
        problem := guard.query_problem(clean["query"], ctx.profile.get("personal_info"))
    ):
        return problem
    return clean


async def propose(
    call: ToolCall,
    tool: registry.Tool,
    label: str,
    ctx: ToolContext,
    proposals: list[ProposalMeta],
    *,
    read_untrusted: bool,
) -> ToolRun:
    """A pending action and its card (appended to ``proposals``, at most ``MAX_PER_TURN`` a
    turn); the model only learns that the user must confirm, or the fixed code of why not."""
    if len(proposals) >= MAX_PER_TURN:
        hint = "Let the user decide on the cards shown."
        return ToolRun({"error": "proposal_limit", "hint": hint}, label, ok=False)
    # ``read_untrusted``: outside text other than the job in focus reached the model this turn
    untrusted = read_untrusted or (ctx.job_id is not None and tool.id not in JOB_BOUND)
    card = await _store(ctx, tool, call.args, untrusted=untrusted)
    if isinstance(card, str):
        wanted = [n for n, req in inputs(tool) if req]
        hint = (
            f"Required: {', '.join(wanted) or 'nothing'}; each value is text up to"
            f" {ARG_CHARS} characters."
            if card == "invalid_arguments"
            else "Nothing was proposed: tell the user why, or rephrase without personal data."
        )
        return ToolRun({"error": card, "hint": hint}, label, ok=False)
    proposals.append(card)
    note = "The user must confirm in the app."
    result = {"status": "proposed", "action_id": str(card.action_id), "note": note}
    return ToolRun(result, label, proposal=card)


async def _store(
    ctx: ToolContext, tool: registry.Tool, args: dict[str, Any], *, untrusted: bool
) -> ProposalMeta | str:
    """Store a pending action, committed so its card can be confirmed at once. A str: the fixed
    code the model gets back instead (bad args, an unknown flow, personal data...)."""
    clean = await _prepare(ctx, tool, args)
    if isinstance(clean, str):
        return clean
    text = summary(tool.id, clean, ctx.job_title, ctx.language)
    action = await repository.add_action(
        ctx.db,
        org_id=ctx.org_id,
        conversation_id=ctx.conversation_id,
        job_id=ctx.job_id,
        tool=tool.id,
        args=clean,
        summary=text,
        untrusted=untrusted,
    )
    await ctx.db.commit()
    logger.info(
        "coach action proposed", extra={"tool": tool.id, "action_id": str(action.id)}
    )
    return ProposalMeta(
        action_id=action.id, tool=tool.id, summary=text, args=clean, untrusted=untrusted
    )


def _stale(created_at: datetime) -> bool:
    return created_at < datetime.now(UTC) - EXPIRES


async def _close(
    db: AsyncSession,
    org_id: UUID,
    action_id: UUID,
    status: str,
    *,
    code: str | None = None,
    result: dict[str, str] | None = None,
) -> None:
    await repository.decide_action(
        db,
        org_id=org_id,
        action_ids=[action_id],
        status=status,
        code=code,
        result=result,
    )
    await db.commit()


async def decide(
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
    helper_off: bool,
) -> ActionOutcome:
    """Run or drop a proposed action, once (the row is locked: a double click waits, then gets
    409). 404 for another org's or an unknown one, 410 after 15 minutes. A refused or failed run
    is an outcome with a fixed code, never exception text. ``helper_off``: the chat's helper was
    archived or helpers switched off since: nothing it proposed runs."""
    action = await repository.lock_action(
        db, org_id=org_id, conversation_id=conversation_id, action_id=action_id
    )
    if action is None:
        raise NotFound("Action not found.")
    status = _status(action.status, action.created_at)
    if status == "expired":
        if action.status == "pending":
            await _close(db, org_id, action_id, "expired")
        raise ActionExpired()
    if status != "pending":
        raise ActionDecided()
    if decision == "cancel":
        await _close(db, org_id, action_id, "cancelled")
        return ActionOutcome(status="cancelled")
    tool = registry.all().get(action.tool)
    call = registry.Call(db, llm, org_id, user_id, action.job_id, dict(action.args))
    done = _DONE[language].format(summary=action.summary)
    code = (
        "tool_off"
        if tool is None or helper_off
        else await _refusal(settings, tool, call, action_id)
    )
    if tool is None or code is not None:
        await _close(db, org_id, action_id, "failed", code=code)
        logger.info(
            "coach action refused", extra={"action_id": str(action_id), "code": code}
        )
        return ActionOutcome(status="failed", code=code)
    # claimed: never run twice, even on a crash
    await _close(db, org_id, action_id, "done")
    return await _run(tool, call, conversation_id, action_id, done)


async def _refusal(
    settings: Settings, tool: registry.Tool, call: registry.Call, action_id: UUID
) -> str | None:
    """Why it cannot run now, or None: then its daily cap use is recorded in the flows' ledger
    (one budget for flows and chat), in the caller's transaction."""
    if (
        not settings.coach_job_focus
        or not tool.chat
        or tool.effect == "outside"
        or (tool.flag is not None and not getattr(settings, tool.flag))
    ):
        return "tool_off"
    if tool.needs_job and call.job_id is None:
        return "no_job"
    if tool.cap is not None:
        verdict = (
            "capped"  # a cap is per user: no user, no use
            if call.user_id is None
            else await flows.claim_effect(
                call.db,
                org_id=call.org_id,
                user_id=call.user_id,
                run_id=None,
                node_id=action_id,
                kind=tool.id,
                daily_cap=tool.cap.user,
                global_cap=tool.cap.everyone,
                once=tool.cap.once,
            )
        )
        if verdict == "capped":
            return "cap_reached"
    return None


async def _run(
    tool: registry.Tool,
    call: registry.Call,
    conversation_id: UUID,
    action_id: UUID,
    done: str,
) -> ActionOutcome:
    """The registry handler, as a flow step runs it (AI uses go through the gateway's quota).
    The chat then says what was done, in a message the server wrote."""
    db, org_id = call.db, call.org_id
    try:
        out = await tool_calls.invoke(tool, call)
    except Exception as exc:  # noqa: BLE001  (a fixed code, never exception text)
        code = exc.code if isinstance(exc, AppError) else "tool_failed"
        logger.warning(
            "coach action failed",
            extra={"tool": tool.id, "code": code, "error_type": type(exc).__name__},
        )
        await db.rollback()  # loaded rows expire: only plain values are used below
        await _close(db, org_id, action_id, "failed", code=code)
        return ActionOutcome(status="failed", code=code)
    # only the ids the run produced (for links): no tool text is kept or sent back
    result = {k: visible(str(v)) for k, v in out.items() if k.endswith("_id")} or None
    await repository.decide_action(
        db, org_id=org_id, action_ids=[action_id], status="done", result=result
    )
    await repository.add_assistant_message(
        db, org_id=org_id, conversation_id=conversation_id, content=done
    )
    await db.commit()
    logger.info(
        "coach action done", extra={"tool": tool.id, "action_id": str(action_id)}
    )
    return ActionOutcome(status="done", result=result)


State = tuple[ActionStatus, str | None, dict[str, str] | None]


def _status(stored: str, created_at: datetime) -> ActionStatus:
    """The DB CHECK keeps ``stored`` one of the five; a pending one past 15 min reads expired."""
    if stored == "pending" and _stale(created_at):
        return "expired"
    return cast(ActionStatus, stored)


async def states(
    db: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> dict[UUID, State]:
    """Each action's live (status, code, result ids), to re-render cards; a pending one past
    15 min is expired."""
    rows = await repository.action_states(
        db, org_id=org_id, conversation_id=conversation_id
    )
    return {i: (_status(s, at), c, r) for i, s, c, at, r in rows}


async def drop_pending(
    db: AsyncSession, *, org_id: UUID, metas: list[dict[str, Any] | None]
) -> None:
    """A regenerated reply's cards leave the chat: their pending actions are cancelled (in the
    caller's transaction)."""
    ids = [
        UUID(card["action_id"]) for m in metas for card in (m or {}).get("actions", [])
    ]
    if ids:
        await repository.decide_action(
            db, org_id=org_id, action_ids=ids, status="cancelled", only_pending=True
        )
