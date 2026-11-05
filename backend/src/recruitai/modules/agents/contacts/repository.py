"""SQL for email recipients and the platform-wide suppression list (ADR 0032)."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.agents.contacts.models import (
    EmailInvite,
    EmailRecipient,
    EmailSuppression,
)


async def list_for_user(
    session: AsyncSession, *, org_id: UUID, user_id: UUID
) -> list[EmailRecipient]:
    rows = await session.execute(
        select(EmailRecipient)
        .where(EmailRecipient.org_id == org_id, EmailRecipient.user_id == user_id)
        .order_by(EmailRecipient.created_at)
    )
    return list(rows.scalars())


async def get_by_email(
    session: AsyncSession, *, org_id: UUID, user_id: UUID, email: str
) -> EmailRecipient | None:
    return (
        await session.execute(
            select(EmailRecipient).where(
                EmailRecipient.org_id == org_id,
                EmailRecipient.user_id == user_id,
                EmailRecipient.email == email,
            )
        )
    ).scalar_one_or_none()


async def count_for_user(session: AsyncSession, *, user_id: UUID) -> int:
    return (
        await session.execute(
            select(func.count(EmailRecipient.id)).where(
                EmailRecipient.user_id == user_id
            )
        )
    ).scalar_one()


async def create(
    session: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    email: str,
    confirm_hash: str,
    unsubscribe_token: str,
) -> EmailRecipient:
    row = EmailRecipient(
        org_id=org_id,
        user_id=user_id,
        email=email,
        confirm_hash=confirm_hash,
        unsubscribe_token=unsubscribe_token,
    )
    session.add(row)
    await session.flush()
    return row


async def delete_one(
    session: AsyncSession, *, org_id: UUID, user_id: UUID, recipient_id: UUID
) -> bool:
    result = await session.execute(
        delete(EmailRecipient)
        .where(
            EmailRecipient.id == recipient_id,
            EmailRecipient.org_id == org_id,
            EmailRecipient.user_id == user_id,
        )
        .returning(EmailRecipient.id)
    )
    return result.first() is not None


async def by_confirm_hash(
    session: AsyncSession, *, confirm_hash: str
) -> EmailRecipient | None:
    return (
        await session.execute(
            select(EmailRecipient).where(EmailRecipient.confirm_hash == confirm_hash)
        )
    ).scalar_one_or_none()


async def by_unsubscribe_token(
    session: AsyncSession, *, token: str
) -> EmailRecipient | None:
    return (
        await session.execute(
            select(EmailRecipient).where(EmailRecipient.unsubscribe_token == token)
        )
    ).scalar_one_or_none()


async def is_suppressed(session: AsyncSession, *, email_hash: str) -> bool:
    return (
        await session.execute(
            select(EmailSuppression.email_hash).where(
                EmailSuppression.email_hash == email_hash
            )
        )
    ).first() is not None


async def suppress_everywhere(
    session: AsyncSession, *, email: str, email_hash: str
) -> None:
    """The address asked to stop: block it for the whole platform and drop it from every list."""
    await session.execute(
        pg_insert(EmailSuppression)
        .values(email_hash=email_hash)
        .on_conflict_do_nothing()
    )
    await session.execute(delete(EmailRecipient).where(EmailRecipient.email == email))


async def one_hour_ago(session: AsyncSession) -> datetime:
    return (await session.execute(select(func.now() - timedelta(hours=1)))).scalar_one()


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[EmailRecipient]:
    rows = await session.execute(
        select(EmailRecipient).where(EmailRecipient.org_id == org_id)
    )
    return list(rows.scalars())


async def lock_invites(session: AsyncSession) -> None:
    """One short critical section for the platform-wide invite cap (released at commit)."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended("email_invites", 0)))
    )


async def count_invites_today(
    session: AsyncSession, *, user_id: UUID | None = None, email_hash: str | None = None
) -> int:
    """Confirmation mails sent today: by everyone, by one user, or to one address."""
    query = select(func.count(EmailInvite.id)).where(
        EmailInvite.created_at >= func.date_trunc("day", func.now())
    )
    if user_id is not None:
        query = query.where(EmailInvite.user_id == user_id)
    if email_hash is not None:
        query = query.where(EmailInvite.email_hash == email_hash)
    return (await session.execute(query)).scalar_one()


async def add_invite(session: AsyncSession, *, user_id: UUID, email_hash: str) -> None:
    session.add(EmailInvite(user_id=user_id, email_hash=email_hash))
    await session.flush()
