"""``identity:send_application_reminders``: the daily digest of follow-ups and interviews.

Scheduled, idempotent per day (an item is due on one day only), no ``task_runs`` row: nobody
polls housekeeping. Failures are logged by type only; the next day's run simply continues."""

from datetime import UTC, datetime

import procrastinate

from recruitai.modules.identity import service
from recruitai.modules.radar import service as radar

blueprint = procrastinate.Blueprint()


@blueprint.periodic(cron="0 8 * * *")
@blueprint.task(name="send_application_reminders")
async def send_application_reminders(timestamp: int) -> None:
    from recruitai.config import get_settings
    from recruitai.core.email import get_email_sender
    from recruitai.worker import session_factory

    now = datetime.now(UTC)
    async with session_factory() as session:
        await service.send_application_reminders(
            session,
            get_email_sender(get_settings()),
            now=now,
            extra_lines=await radar.new_match_lines(session, now=now),
        )
