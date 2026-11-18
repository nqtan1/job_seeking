"""The Assistant inbox (ADR 0042): the one ``core.inbox`` sink, registered on import (``packs.py``
imports this for the API and the worker). An item is an ordinary assistant message in the org's
Assistant conversation, with ``meta.inbox = {kind, link}`` and server-built text: no model call, so
export and deletion cover it like any message. When the user linked Telegram, a task mirrors the
line there after the commit (enqueued in the caller's transaction, so a rollback sends nothing)."""

from datetime import UTC, datetime
from uuid import UUID

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import get_settings
from recruitai.core import inbox
from recruitai.core import tools as registry
from recruitai.core.errors import NotFound
from recruitai.core.language import Language
from recruitai.core.tasks import enqueue, mark_done, mark_failed
from recruitai.core.telegram import MAX_MESSAGE, Telegram, TelegramError
from recruitai.modules.candidates import service as candidates
from recruitai.modules.coach import repository
from recruitai.modules.coach.models import Conversation
from recruitai.modules.coach.schemas import InboxMeta, MessageMeta
from recruitai.modules.identity import service as identity

blueprint = procrastinate.Blueprint()  # registered by the worker, namespace "coach"
TELEGRAM_TASK = "coach:telegram_line"
TEMPLATE_VERSION = "inbox-v1"  # the text is a server template: no prompt, no model
MAX_TEXT = 500
_TEXT: dict[inbox.Kind, dict[Language, str]] = {
    "run_done": {
        "en": "{name}: done.",
        "fr": "{name} : terminé.",
        "vi": "{name}: đã xong.",
    },
    "run_failed": {
        "en": "{name}: failed ({code}).",
        "fr": "{name} : échec ({code}).",
        "vi": "{name}: thất bại ({code}).",
    },
    "reminder": {
        "en": "Reminders: {count} follow-up(s) or interview(s) today.",
        "fr": "Rappels : {count} relance(s) ou entretien(s) aujourd'hui.",
        "vi": "Nhắc việc: {count} lần theo dõi hoặc phỏng vấn hôm nay.",
    },
}


async def _telegram_chat(db: AsyncSession, org_id: UUID, user_id: UUID) -> int | None:
    """The user's linked chat, through the registry (agents owns connections, ADR 0039)."""
    got = await registry.read(
        "telegram_chat", registry.Call(db, None, org_id, user_id, None, {})
    )
    return int(got["chat_id"]) if got else None


async def assistant_conversation(db: AsyncSession, *, org_id: UUID) -> Conversation:
    """Get or create; a conversation belongs to a profile, so none before a CV (422)."""
    profile = await candidates.require_profile(db, org_id=org_id)
    return await repository.assistant_conversation(
        db, org_id=org_id, candidate_id=profile.id
    )


async def _post(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    kind: inbox.Kind,
    params: dict[str, str | int],
    link: str | None,
) -> None:
    # ponytail: no CV means no conversation to post into; a profile-less inbox if that bites
    try:
        profile = await candidates.get_profile(db, org_id=org_id)
    except NotFound:
        return
    conversation = await repository.assistant_conversation(
        db, org_id=org_id, candidate_id=profile.id
    )
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "reminder" and await repository.inbox_posted_since(
        db, org_id=org_id, conversation_id=conversation.id, kind=kind, since=today
    ):
        return  # one reminder a day (UTC, like the digest), even if the task runs twice
    meta = MessageMeta(
        prompt_version=TEMPLATE_VERSION,
        model="none",
        inbox=InboxMeta(kind=kind, link=link),
    )
    message = await repository.add_assistant_message(
        db,
        org_id=org_id,
        conversation_id=conversation.id,
        content=_TEXT[kind][await identity.user_language(db, user_id)].format_map(
            {k: registry.one_line(str(v))[:80] for k, v in params.items()}
        )[:MAX_TEXT],
        meta=meta.model_dump(mode="json"),
    )
    # connections are part of agents: switched off, nothing goes to Telegram
    if (
        not get_settings().helpers_enabled
        or await _telegram_chat(db, org_id, user_id) is None
    ):
        return
    await enqueue(
        db,
        task=TELEGRAM_TASK,
        org_id=org_id,
        kind="coach.telegram_line",
        task_kwargs={
            "org_id": str(org_id),
            "user_id": str(user_id),
            "message_id": str(message.id),
        },
    )


inbox.register_sink(_post)


async def mirror(
    db: AsyncSession,
    bot: Telegram,
    base_url: str,
    *,
    org_id: UUID,
    user_id: UUID,
    message_id: UUID,
) -> str | None:
    """Send the inbox line to the user's linked chat: None when sent or nothing to send (unlinked
    or deleted since), else a fixed code. Read at send time, so the job holds only ids."""
    chat_id = await _telegram_chat(db, org_id, user_id)
    message = await repository.get_message(db, org_id=org_id, message_id=message_id)
    if chat_id is None or message is None:
        return None
    link = ((message.meta or {}).get("inbox") or {}).get("link")
    line = message.content + (f"\n{base_url}{link}" if link else "")
    await db.commit()  # nothing held open while Telegram answers
    try:
        await bot.send(chat_id, line[:MAX_MESSAGE])
    except TelegramError as exc:
        return "telegram_blocked" if exc.blocked else "telegram_failed"
    return None


@blueprint.task(name="telegram_line")
async def telegram_line(
    task_run_id: str, org_id: str, user_id: str, message_id: str
) -> None:
    """Not retried: a blind retry after an unanswered send could deliver the line twice."""
    from recruitai.core.telegram import get_telegram
    from recruitai.worker import session_factory

    settings = get_settings()
    bot = get_telegram(settings)
    async with session_factory() as session:
        code = None
        if bot is not None:  # no bot configured: the inbox message is the whole item
            code = await mirror(
                session,
                bot,
                settings.app_base_url,
                org_id=UUID(org_id),
                user_id=UUID(user_id),
                message_id=UUID(message_id),
            )
        if code is None:
            await mark_done(session, UUID(task_run_id))
        else:
            await mark_failed(session, UUID(task_run_id), error_code=code)
