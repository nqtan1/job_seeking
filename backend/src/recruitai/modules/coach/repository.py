"""All SQL for the coach module. Every query filters by org_id."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.coach.models import Conversation, Message


async def create_conversation(
    session: AsyncSession, *, org_id: UUID, candidate_id: UUID, job_id: UUID | None
) -> Conversation:
    conversation = Conversation(org_id=org_id, candidate_id=candidate_id, job_id=job_id)
    session.add(conversation)
    await session.flush()
    await session.refresh(conversation)  # server-side started_at
    return conversation


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
) -> list[Message]:
    """The two messages of one turn, in the caller's transaction. Timestamps are explicit and
    1 ms apart, and always after the conversation's latest message: with ``now()`` both rows
    would tie, and turns stored within a millisecond of each other could interleave."""
    # Serialize turns of one conversation while storing: two simultaneous messages would
    # otherwise compute the same "latest" and could interleave their rows.
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
    if latest is not None:
        now = max(now, latest + timedelta(milliseconds=1))
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
    session.add_all(rows)
    await session.flush()
    return rows


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
) -> list[Message]:
    rows = await session.execute(
        select(Message)
        .where(Message.org_id == org_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


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
