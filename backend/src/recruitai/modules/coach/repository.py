"""All SQL for the coach module. Every query filters by org_id."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.ids import new_id
from recruitai.modules.coach.models import CoachAction, Conversation, Message


async def create_conversation(
    session: AsyncSession,
    *,
    org_id: UUID,
    candidate_id: UUID,
    job_id: UUID | None,
    agent_id: UUID | None = None,
) -> Conversation:
    conversation = Conversation(
        org_id=org_id, candidate_id=candidate_id, job_id=job_id, agent_id=agent_id
    )
    session.add(conversation)
    await session.flush()
    await session.refresh(conversation)  # server-side started_at
    return conversation


async def assistant_conversation(
    session: AsyncSession, *, org_id: UUID, candidate_id: UUID
) -> Conversation:
    """The org's one Assistant conversation, created on first use. Two first uses at once both
    insert; the partial unique index keeps one and the other reads it."""
    await session.execute(
        insert(Conversation)
        .values(id=new_id(), org_id=org_id, candidate_id=candidate_id, kind="assistant")
        .on_conflict_do_nothing(
            index_elements=["org_id"], index_where=text("kind = 'assistant'")
        )
    )
    return (
        await session.execute(
            select(Conversation).where(
                Conversation.org_id == org_id, Conversation.kind == "assistant"
            )
        )
    ).scalar_one()


async def inbox_posted_since(
    session: AsyncSession,
    *,
    org_id: UUID,
    conversation_id: UUID,
    kind: str,
    since: datetime,
) -> bool:
    found = await session.scalar(
        select(Message.id)
        .where(
            Message.org_id == org_id,
            Message.conversation_id == conversation_id,
            Message.created_at >= since,
            Message.meta["inbox"]["kind"].astext == kind,
        )
        .limit(1)
    )
    return found is not None


async def get_message(
    session: AsyncSession, *, org_id: UUID, message_id: UUID
) -> Message | None:
    return await session.scalar(
        select(Message).where(Message.org_id == org_id, Message.id == message_id)
    )


async def get_conversation(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> Conversation | None:
    return (
        await session.execute(
            select(Conversation).where(
                Conversation.org_id == org_id, Conversation.id == conversation_id
            )
        )
    ).scalar_one_or_none()


async def list_conversations(
    session: AsyncSession, *, org_id: UUID, limit: int, offset: int
) -> list[tuple[Conversation, str | None, datetime]]:
    """Newest activity first. The title is the first user message, so no extra column."""
    first = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id, Message.role == "user")
        .order_by(Message.created_at)
        .limit(1)
        .scalar_subquery()
    )
    last = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    updated = func.coalesce(last, Conversation.started_at)
    rows = await session.execute(
        select(Conversation, first, updated)
        .where(Conversation.org_id == org_id)
        .order_by(updated.desc(), Conversation.id)
        .limit(limit)
        .offset(offset)
    )
    return [(c, title, at) for c, title, at in rows.all()]


async def add_turn(
    session: AsyncSession,
    *,
    org_id: UUID,
    conversation_id: UUID,
    user_text: str,
    assistant_text: str,
    assistant_meta: dict[str, Any] | None = None,
) -> list[Message]:
    """The two messages of one turn, in the caller's transaction. Timestamps are explicit and
    1 ms apart, and always after the conversation's latest message: with ``now()`` both rows
    would tie, and turns stored within a millisecond of each other could interleave."""
    now = await _next_at(session, org_id=org_id, conversation_id=conversation_id)
    rows = [
        Message(
            conversation_id=conversation_id,
            org_id=org_id,
            role=role,
            content=text,
            created_at=now + timedelta(milliseconds=offset),
        )
        for role, text, offset in (
            ("user", user_text, 0),
            ("assistant", assistant_text, 1),
        )
    ]
    rows[1].meta = assistant_meta
    session.add_all(rows)
    await session.flush()
    return rows


async def _next_at(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> datetime:
    """Now, or 1 ms after the conversation's latest message. Locks the conversation row: two
    simultaneous writes would otherwise compute the same "latest" and could interleave."""
    await session.execute(
        select(Conversation.id)
        .where(Conversation.org_id == org_id, Conversation.id == conversation_id)
        .with_for_update()
    )
    now = datetime.now(UTC)
    latest = await session.scalar(
        select(func.max(Message.created_at)).where(
            Message.org_id == org_id, Message.conversation_id == conversation_id
        )
    )
    return now if latest is None else max(now, latest + timedelta(milliseconds=1))


async def add_assistant_message(
    session: AsyncSession,
    *,
    org_id: UUID,
    conversation_id: UUID,
    content: str,
    meta: dict[str, Any] | None = None,
) -> Message:
    """A server-built line in the chat (a confirmed action's outcome, an inbox item), in the
    caller's transaction."""
    at = await _next_at(session, org_id=org_id, conversation_id=conversation_id)
    message = Message(
        conversation_id=conversation_id,
        org_id=org_id,
        role="assistant",
        content=content,
        created_at=at,
        meta=meta,
    )
    session.add(message)
    await session.flush()
    return message


async def add_action(session: AsyncSession, **values: Any) -> CoachAction:
    action = CoachAction(**values)
    session.add(action)
    await session.flush()
    return action


async def lock_action(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID, action_id: UUID
) -> CoachAction | None:
    """The action, locked until the caller's commit (a double click waits here)."""
    return (
        await session.execute(
            select(CoachAction)
            .where(
                CoachAction.org_id == org_id,
                CoachAction.conversation_id == conversation_id,
                CoachAction.id == action_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)  # the row as locked
        )
    ).scalar_one_or_none()


async def decide_action(
    session: AsyncSession,
    *,
    org_id: UUID,
    action_ids: list[UUID],
    status: str,
    code: str | None = None,
    result: dict[str, str] | None = None,
    only_pending: bool = False,
) -> None:
    query = update(CoachAction).where(
        CoachAction.org_id == org_id, CoachAction.id.in_(action_ids)
    )
    if only_pending:
        query = query.where(CoachAction.status == "pending")
    await session.execute(
        query.values(status=status, code=code, result=result, decided_at=func.now())
    )


async def action_states(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> list[tuple[UUID, str, str | None, datetime, dict[str, Any] | None]]:
    """(id, status, code, created_at, result) of the conversation's actions."""
    rows = await session.execute(
        select(
            CoachAction.id,
            CoachAction.status,
            CoachAction.code,
            CoachAction.created_at,
            CoachAction.result,
        ).where(
            CoachAction.org_id == org_id, CoachAction.conversation_id == conversation_id
        )
    )
    return [(i, s, c, at, r) for i, s, c, at, r in rows.all()]


async def all_actions(session: AsyncSession, *, org_id: UUID) -> list[CoachAction]:
    rows = await session.execute(
        select(CoachAction)
        .where(CoachAction.org_id == org_id)
        .order_by(CoachAction.conversation_id, CoachAction.created_at)
    )
    return list(rows.scalars())


async def recent_messages(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID, limit: int
) -> list[Message]:
    """The last ``limit`` messages, oldest first."""
    rows = await session.execute(
        select(Message)
        .where(Message.org_id == org_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows.scalars())))


async def list_messages(
    session: AsyncSession,
    *,
    org_id: UUID,
    conversation_id: UUID,
    limit: int,
    offset: int,
    latest: bool = False,
) -> list[Message]:
    """Oldest first; ``latest``: the newest ``limit`` (still oldest first in the list)."""
    order = (
        (Message.created_at.desc(), Message.id.desc())
        if latest
        else (Message.created_at, Message.id)
    )
    rows = await session.execute(
        select(Message)
        .where(Message.org_id == org_id, Message.conversation_id == conversation_id)
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    )
    out = list(rows.scalars())
    return out[::-1] if latest else out


async def all_conversations(
    session: AsyncSession, *, org_id: UUID
) -> list[Conversation]:
    rows = await session.execute(
        select(Conversation)
        .where(Conversation.org_id == org_id)
        .order_by(Conversation.started_at)
    )
    return list(rows.scalars())


async def all_messages(session: AsyncSession, *, org_id: UUID) -> list[Message]:
    rows = await session.execute(
        select(Message)
        .where(Message.org_id == org_id)
        .order_by(Message.conversation_id, Message.created_at, Message.id)
    )
    return list(rows.scalars())


async def set_job(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID, job_id: UUID | None
) -> None:
    await session.execute(
        update(Conversation)
        .where(Conversation.org_id == org_id, Conversation.id == conversation_id)
        .values(job_id=job_id)
    )


async def delete_conversation(
    session: AsyncSession, *, org_id: UUID, conversation_id: UUID
) -> None:
    """Messages go with it (``ON DELETE CASCADE``)."""
    await session.execute(
        delete(Conversation).where(
            Conversation.org_id == org_id, Conversation.id == conversation_id
        )
    )


async def delete_messages(
    session: AsyncSession, *, org_id: UUID, message_ids: list[UUID]
) -> int:
    """How many were deleted (fewer than asked means someone else already removed them)."""
    result = await session.execute(
        delete(Message).where(Message.org_id == org_id, Message.id.in_(message_ids))
    )
    return int(result.rowcount)  # type: ignore[attr-defined]  # CursorResult for a DELETE
