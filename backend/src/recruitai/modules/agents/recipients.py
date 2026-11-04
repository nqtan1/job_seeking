"""Who a flow may email (ADR 0032). An address is allowed only if the user added it and the address's
owner confirmed it with a one-time link; and never once it asked to stop (the suppression list is platform-wide and holds hashes, not addresses).
The confirmation and unsubscribe links are the only way an outsider touches the system.
There is no "own address" shortcut: the user adds their own address and confirms it like any other."""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings
from recruitai.core.email import EmailSender
from recruitai.core.errors import Conflict, NotFound, ValidationFailed
from recruitai.core.tenancy import OrgContext
from recruitai.modules.agents import recipients_repository as repo
from recruitai.modules.agents.models import EmailRecipient
from recruitai.modules.identity import service as identity

MAX_RECIPIENTS = 20
# Confirmation mail goes to people who never asked for it, so it is the tightest limit we have:
MAX_INVITES_PER_USER_DAY = 10
MAX_INVITES_PER_ADDRESS_DAY = 3  # one victim cannot be bombed from many accounts
MAX_INVITES_PER_DAY = 300  # everyone together
CONFIRM_VALID_DAYS = 7
# One address, no names, no quotes, no list separators, no spaces or line breaks.
ADDRESS = re.compile(r"[^\s@<>\"',;:()\[\]\\]{1,64}@[a-z0-9.-]{1,190}\.[a-z]{2,24}")


def normalize(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or not ADDRESS.fullmatch(email):
        raise ValidationFailed("Enter one valid email address.")
    return email


def email_hash(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def list_recipients(db: AsyncSession, ctx: OrgContext) -> list[EmailRecipient]:
    return await repo.list_for_user(db, org_id=ctx.org_id, user_id=ctx.user_id)


async def add_recipient(
    db: AsyncSession,
    ctx: OrgContext,
    raw: str,
    *,
    sender: EmailSender,
    settings: Settings,
) -> EmailRecipient:
    email = normalize(raw)
    digest = email_hash(email)
    token = secrets.token_urlsafe(32)
    row = await repo.get_by_email(
        db, org_id=ctx.org_id, user_id=ctx.user_id, email=email
    )
    if row is not None and row.status == "confirmed":
        return row
    if row is not None:  # pending: a new link at most once an hour
        if row.created_at > await repo.one_hour_ago(db):
            raise Conflict("A confirmation email was sent a moment ago.")
    elif await repo.count_for_user(db, user_id=ctx.user_id) >= MAX_RECIPIENTS:
        raise Conflict(f"You can have at most {MAX_RECIPIENTS} recipients.")
    if await repo.is_suppressed(db, email_hash=digest):
        # Same answer as for any address, and nothing is sent: nobody can use this to learn who
        # asked to stop. The row can never be confirmed (``confirm`` refuses it).
        if row is None:
            await repo.create(
                db,
                org_id=ctx.org_id,
                user_id=ctx.user_id,
                email=email,
                confirm_hash=_token_hash(token),
                unsubscribe_token=secrets.token_urlsafe(32),
            )
        await db.commit()
        return await _must(db, ctx, email)
    # Every confirmation mail (first or repeated) is one invite in a ledger nobody can erase.
    await repo.lock_invites(db)
    if (
        await repo.count_invites_today(db, user_id=ctx.user_id)
        >= MAX_INVITES_PER_USER_DAY
        or await repo.count_invites_today(db, email_hash=digest)
        >= MAX_INVITES_PER_ADDRESS_DAY
        or await repo.count_invites_today(db) >= MAX_INVITES_PER_DAY
    ):
        raise Conflict("Too many confirmation emails today. Try again tomorrow.")
    await repo.add_invite(db, user_id=ctx.user_id, email_hash=digest)
    new = row is None
    if row is None:
        row = await repo.create(
            db,
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            email=email,
            confirm_hash=_token_hash(token),
            unsubscribe_token=secrets.token_urlsafe(32),
        )
    else:
        row.confirm_hash = _token_hash(token)
        row.created_at = datetime.now(UTC)
    await db.commit()
    row_id, unsub = row.id, row.unsubscribe_token
    try:
        await sender.send(
            email,
            "recipient_confirm",
            {
                "language": (language := await identity.user_language(db, ctx.user_id)),
                "sender_email": await sender_label(db, ctx.user_id, language),
                "link": f"{settings.app_base_url}/api/public/email/confirm?t={token}",
                "block_url": f"{settings.app_base_url}/api/public/email/unsubscribe?t={unsub}",
            },
        )
    except Exception:
        if new:  # nothing was sent: do not make the user wait an hour to try again
            await repo.delete_one(
                db, org_id=ctx.org_id, user_id=ctx.user_id, recipient_id=row_id
            )
            await db.commit()
        raise
    return row


async def _must(db: AsyncSession, ctx: OrgContext, email: str) -> EmailRecipient:
    row = await repo.get_by_email(
        db, org_id=ctx.org_id, user_id=ctx.user_id, email=email
    )
    assert row is not None
    return row


_SOMEONE = {
    "en": "a RecruitAI user",
    "fr": "un utilisateur de RecruitAI",
    "vi": "một người dùng RecruitAI",
}


async def sender_label(db: AsyncSession, user_id: UUID, language: str) -> str:
    """Who an outsider is told is writing: the address only if its owner verified it (an account
    can be opened with anyone's address), otherwise a plain "a RecruitAI user"."""
    shown = await identity.verified_email_of(db, user_id=user_id)
    return shown or _SOMEONE.get(language, _SOMEONE["en"])


async def remove_recipient(
    db: AsyncSession, ctx: OrgContext, recipient_id: UUID
) -> None:
    if not await repo.delete_one(
        db, org_id=ctx.org_id, user_id=ctx.user_id, recipient_id=recipient_id
    ):
        raise NotFound("Recipient not found.")
    await db.commit()


async def confirm(db: AsyncSession, token: str) -> bool:
    row = await repo.by_confirm_hash(db, confirm_hash=_token_hash(token))
    if (
        row is None
        or row.created_at < datetime.now(UTC) - timedelta(days=CONFIRM_VALID_DAYS)
        or await repo.is_suppressed(db, email_hash=email_hash(row.email))
    ):
        return False
    row.status, row.confirm_hash = "confirmed", None
    row.confirmed_at = datetime.now(UTC)
    await db.commit()
    return True


async def unsubscribe(db: AsyncSession, token: str) -> bool:
    row = await repo.by_unsubscribe_token(db, token=token)
    if row is None:
        return False
    await repo.suppress_everywhere(
        db, email=row.email, email_hash=email_hash(row.email)
    )
    await db.commit()
    return True


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    unsubscribe_token: str | None = None


async def may_send(
    db: AsyncSession, *, org_id: UUID, user_id: UUID, to: str
) -> Verdict:
    """The one gate in front of every outgoing flow email."""
    if await repo.is_suppressed(db, email_hash=email_hash(to)):
        return Verdict(False)
    row = await repo.get_by_email(db, org_id=org_id, user_id=user_id, email=to)
    if row is None or row.status != "confirmed":
        return Verdict(False)
    return Verdict(True, row.unsubscribe_token)


Page = Literal["confirm", "unsubscribe"]
