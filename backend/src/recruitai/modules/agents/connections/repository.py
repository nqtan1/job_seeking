"""SQL for connections (ADR 0036)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.agents.connections.models import Connection


async def list_for_user(
    session: AsyncSession, *, org_id: UUID, user_id: UUID
) -> list[Connection]:
    rows = await session.execute(
        select(Connection)
        .where(Connection.org_id == org_id, Connection.user_id == user_id)
        .order_by(Connection.created_at)
    )
    return list(rows.scalars())


async def get(
    session: AsyncSession, *, org_id: UUID, user_id: UUID, provider: str
) -> Connection | None:
    return (
        await session.execute(
            select(Connection).where(
                Connection.org_id == org_id,
                Connection.user_id == user_id,
                Connection.provider == provider,
            )
        )
    ).scalar_one_or_none()


async def pending_by_hash(
    session: AsyncSession, *, provider: str, link_hash: str, now: datetime
) -> Connection | None:
    """The link code is the credential: found by its hash, and only while it is still valid."""
    return (
        await session.execute(
            select(Connection).where(
                Connection.provider == provider,
                Connection.status == "pending",
                Connection.link_hash == link_hash,
                Connection.link_expires_at > now,
            )
        )
    ).scalar_one_or_none()


async def chat_is_linked(session: AsyncSession, *, provider: str, chat_id: int) -> bool:
    return (
        await session.execute(
            select(Connection.id).where(
                Connection.provider == provider,
                Connection.status == "active",
                Connection.chat_id == chat_id,
            )
        )
    ).first() is not None


async def add(session: AsyncSession, connection: Connection) -> Connection:
    session.add(connection)
    await session.flush()
    return connection


async def delete_for_user(
    session: AsyncSession, *, org_id: UUID, user_id: UUID, provider: str
) -> int:
    result = await session.execute(
        delete(Connection).where(
            Connection.org_id == org_id,
            Connection.user_id == user_id,
            Connection.provider == provider,
        )
    )
    return int(getattr(result, "rowcount", 0))


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[Connection]:
    rows = await session.execute(select(Connection).where(Connection.org_id == org_id))
    return list(rows.scalars())


async def delete_by_chat(session: AsyncSession, *, provider: str, chat_id: int) -> int:
    result = await session.execute(
        delete(Connection).where(
            Connection.provider == provider,
            Connection.status == "active",
            Connection.chat_id == chat_id,
        )
    )
    return int(getattr(result, "rowcount", 0))
