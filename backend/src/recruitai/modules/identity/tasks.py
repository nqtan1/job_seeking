"""``identity:send_application_reminders``: the daily digest. Idempotent per day, no ``task_runs``
row; failures are logged by type only."""

from datetime import UTC, datetime
from uuid import UUID

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

    settings = get_settings()
    now = datetime.now(UTC)
    secret = settings.radar_link_secret

    def link_for(org_id: UUID, user_id: UUID) -> str:
        token = radar.withdraw_link(
            secret or "",
            org_id=org_id,
            user_id=user_id,
            ttl_s=settings.radar_link_ttl_days * 86400,
        )
        return f"{settings.app_base_url}/radar/link#t={token}"

    async with session_factory() as session:
        await service.send_application_reminders(
            session,
            get_email_sender(settings),
            now=now,
            extra_lines=await radar.new_match_lines(
                session, now=now, link_for=link_for if secret else None
            ),
        )
