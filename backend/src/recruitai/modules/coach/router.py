"""HTTP only. Errors before the first token are problem+json; after it the stream ends with one
``done`` or ``error`` event (stable ``code``, never exception text). No mid-stream resume (ADR 0016)."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import LLMGateway
from recruitai.config import Settings, get_settings
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.errors import (
    AppError,
    Conflict,
    NotFound,
    Unauthorized,
    UpstreamUnavailable,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.logging import get_context
from recruitai.core.ratelimit import limit_ai
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.coach import actions, service
from recruitai.modules.coach.models import Conversation
from recruitai.modules.coach.schemas import (
    ActionDecision,
    ActionOutcome,
    ConversationIn,
    ConversationKind,
    ConversationOut,
    ConversationPatch,
    ConversationSummary,
    FocusJob,
    MessageIn,
    MessageOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/coach", tags=["coach"])


async def _conversation_out(db: AsyncSession, c: Conversation) -> ConversationOut:
    focus = await service.focus_job(db, c)
    return ConversationOut(
        id=c.id,
        candidate_id=c.candidate_id,
        job_id=c.job_id,
        agent_id=c.agent_id,
        kind=cast(ConversationKind, c.kind),  # the DB CHECK: one of two
        started_at=c.started_at,
        focus=FocusJob(job_id=focus[0], title=focus[1], company=focus[2])
        if focus
        else None,
    )


def _event(name: str, data: dict[str, Any]) -> str:
    # json.dumps escapes newlines, so one `data:` line always holds the whole payload.
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error(code: str, detail: str) -> str:
    return _event(
        "error",
        {"code": code, "detail": detail, "request_id": get_context().get("request_id")},
    )


HEARTBEAT_S = 15.0


async def _events(
    replies: AsyncGenerator[tuple[str, dict[str, Any]]],
    first: tuple[str, dict[str, Any]],
) -> AsyncIterator[str]:
    pending: asyncio.Future[tuple[str, dict[str, Any]]] | None = None
    try:
        yield _event(*first)
        while True:
            # A research step can be silent for a while: a comment line every few seconds keeps
            # proxies (Hosting, Cloud Run's front end) from treating the stream as idle.
            pending = asyncio.ensure_future(anext(replies))
            while True:
                done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_S)
                if done:
                    break
                yield ": ping\n\n"
            try:
                name, data = pending.result()
            except StopAsyncIteration:
                break
            finally:
                pending = None
            yield _event(name, data)
    except AppError as exc:
        yield _error(exc.code, exc.detail)
    except Exception as exc:  # noqa: BLE001  (the stream has started: report, don't crash it)
        logger.error("coach stream failed", extra={"error_type": type(exc).__name__})
        yield _error("internal_error", "Something went wrong.")
    finally:
        if pending is not None:
            pending.cancel()
            # let the cancelled ``anext`` finish: closing a generator that is still running fails
            await asyncio.gather(pending, return_exceptions=True)
        await replies.aclose()  # also runs when the client disconnects mid-reply


async def _stream(
    replies: AsyncGenerator[tuple[str, dict[str, Any]]],
) -> StreamingResponse:
    # refusals and first-call errors raise here: problem+json
    try:
        first = await anext(replies)
    except StopAsyncIteration:  # the service raises on an empty reply: defensive
        raise UpstreamUnavailable(
            "The AI provider returned an empty response.", code="ai_response_invalid"
        ) from None
    return StreamingResponse(
        _events(replies, first),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/conversations",
    status_code=201,
    response_model=ConversationOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def create_conversation(
    body: ConversationIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConversationOut:
    conversation = await service.create_conversation(
        db,
        org_id=ctx.org_id,
        job_id=body.job_id,
        agent_id=body.agent_id,
        settings=settings,
    )
    return await _conversation_out(db, conversation)


@router.get(
    "/assistant",
    response_model=ConversationOut,
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def get_assistant(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationOut:
    """The user's Assistant conversation, where run results and reminders land (created on first
    call; needs a profile). Read its messages with ``GET .../conversations/{id}/messages``."""
    conversation = await service.assistant_conversation(db, org_id=ctx.org_id)
    return await _conversation_out(db, conversation)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def get_conversation(
    conversation_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationOut:
    conversation = await service.get_conversation(
        db, org_id=ctx.org_id, conversation_id=conversation_id
    )
    return await _conversation_out(db, conversation)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def patch_conversation(
    conversation_id: UUID,
    body: ConversationPatch,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationOut:
    """Attach, switch or detach the job in focus (one per conversation)."""
    conversation = await service.set_job(
        db, org_id=ctx.org_id, conversation_id=conversation_id, job_id=body.job_id
    )
    return await _conversation_out(db, conversation)


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    responses=problem_responses(Unauthorized),
)
async def list_conversations(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationSummary]:
    rows = await service.list_conversations(
        db, org_id=ctx.org_id, limit=limit, offset=offset
    )
    return [
        ConversationSummary(
            id=c.id,
            job_id=c.job_id,
            kind=cast(ConversationKind, c.kind),
            title=title[:80] if title else None,
            updated_at=at,
        )
        for c, title, at in rows
    ]


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def delete_conversation(
    conversation_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Permanently deletes the conversation and all its messages."""
    await service.delete_conversation(
        db, org_id=ctx.org_id, conversation_id=conversation_id
    )
    return Response(status_code=204)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_messages(
    conversation_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    latest: bool = False,  # the newest `limit` messages (the Home inbox)
) -> list[MessageOut]:
    return await service.list_messages(
        db,
        org_id=ctx.org_id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        latest=latest,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    # App Check: every message costs an LLM call (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    response_class=StreamingResponse,
    responses={
        **problem_responses(
            Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
        ),
        200: {
            "description": "Server-Sent Events: `token` {text}, `proposal` {action_id, tool, summary, args, untrusted} (a card to confirm), then one `done` or `error` {code, detail}.",
            "content": {"text/event-stream": {}},
        },
    },
)
async def send_message(
    conversation_id: UUID,
    body: MessageIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    return await _stream(
        service.stream_reply(
            db,
            llm,
            settings,
            org_id=ctx.org_id,
            conversation_id=conversation_id,
            content=body.content,
            language=ctx.language,
            user_id=ctx.user_id,
        )
    )


@router.post(
    "/conversations/{conversation_id}/regenerate",
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    response_class=StreamingResponse,
    responses={
        **problem_responses(
            Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
        ),
        200: {
            "description": "Server-Sent Events, as for a new message; replaces the last reply.",
            "content": {"text/event-stream": {}},
        },
    },
)
async def regenerate(
    conversation_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    return await _stream(
        service.stream_reply(
            db,
            llm,
            settings,
            org_id=ctx.org_id,
            conversation_id=conversation_id,
            content=None,
            replace_last=True,
            language=ctx.language,
            user_id=ctx.user_id,
        )
    )


@router.post(
    "/conversations/{conversation_id}/actions/{action_id}",
    # confirming can spend model calls (fit check, letter, offer search)
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    response_model=ActionOutcome,
    responses=problem_responses(
        Unauthorized, NotFound, Conflict, actions.ActionExpired
    ),
)
async def decide_action(
    conversation_id: UUID,
    action_id: UUID,
    body: ActionDecision,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ActionOutcome:
    """Confirm (runs it, once) or cancel an action the chat proposed. 409 once decided, 410 after
    15 minutes. A refused or failed run is a 200 with ``status: failed`` and a fixed ``code``."""
    return await service.decide_action(
        db,
        llm,
        settings,
        org_id=ctx.org_id,
        user_id=ctx.user_id,
        conversation_id=conversation_id,
        action_id=action_id,
        decision=body.decision,
        language=ctx.language,
    )
