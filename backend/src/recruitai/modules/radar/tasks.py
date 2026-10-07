"""``radar:run_search``: one run of one saved search, in the worker (ADR 0021).

``service.run_search`` closes its own ``radar_runs`` row whatever happens, so the task is not
retried: a second attempt would only spend more model calls. A failure that never reaches the
service (the search was deleted meanwhile) becomes a safe ``error_code`` on ``task_runs``."""

import logging
from uuid import UUID

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway
from recruitai.config import Settings
from recruitai.core.errors import AppError
from recruitai.core.tasks import mark_done, mark_failed
from recruitai.modules.radar import service

logger = logging.getLogger(__name__)

blueprint = procrastinate.Blueprint()


async def _llm_for(
    settings: Settings, session: AsyncSession, org_id: UUID, user_id: UUID
) -> LLMGateway:
    """A tenant-bound gateway on the effective settings (config.yaml + admin overrides)."""
    from recruitai.ai.dependencies import build_llm_gateway
    from recruitai.ai.overrides import effective_settings

    return build_llm_gateway(
        await effective_settings(settings, session),
        session,
        org_id=org_id,
        user_id=user_id,
    )


@blueprint.task(name="run_search")
async def run_search(
    task_run_id: str, org_id: str, user_id: str, search_id: str
) -> None:
    from recruitai.config import get_settings
    from recruitai.modules.jobs.providers.factory import france_travail_provider
    from recruitai.worker import session_factory

    settings = get_settings()
    run_id = UUID(task_run_id)
    async with session_factory() as session:
        try:
            run = await service.run_search(
                session,
                await _llm_for(settings, session, UUID(org_id), UUID(user_id)),
                france_travail_provider(),
                org_id=UUID(org_id),
                user_id=UUID(user_id),
                search_id=UUID(search_id),
                quota=settings.ai_daily_quota_per_user,
            )
        except (
            AppError
        ) as exc:  # e.g. NotFound: the search was deleted after it was queued
            await session.rollback()
            await mark_failed(session, run_id, error_code=exc.code)
            return
        except Exception as exc:  # noqa: BLE001  (a safe code, never exception text)
            await session.rollback()
            logger.error("radar task failed", extra={"error_type": type(exc).__name__})
            await mark_failed(session, run_id, error_code="radar_failed")
            return
        await mark_done(session, run_id, result_ref=str(run.id) if run else None)


@blueprint.periodic(
    cron="30 6 * * *"
)  # before the 08:00 reminder digest, which lists the matches
@blueprint.task(name="run_all")
async def run_all(timestamp: int) -> None:
    from recruitai.config import get_settings
    from recruitai.modules.jobs.providers.factory import france_travail_provider
    from recruitai.worker import session_factory

    settings = get_settings()
    if not settings.radar_enabled or not settings.france_travail_client_id:
        return  # off, or no job source configured: nothing to run (and no noise in the logs)
    await service.run_due_searches(
        session_factory,
        lambda session, org_id, user_id: _llm_for(settings, session, org_id, user_id),
        france_travail_provider(),
        quota=settings.ai_daily_quota_per_user,
    )


@blueprint.periodic(
    cron="*/30 * * * *"
)  # an interrupted run is tried again, up to 3 times a day
@blueprint.task(name="retry_interrupted")
async def retry_interrupted(timestamp: int) -> None:
    from recruitai.config import get_settings
    from recruitai.modules.jobs.providers.factory import france_travail_provider
    from recruitai.worker import session_factory

    settings = get_settings()
    if not settings.radar_enabled or not settings.france_travail_client_id:
        return
    await service.retry_interrupted_searches(
        session_factory,
        lambda session, org_id, user_id: _llm_for(settings, session, org_id, user_id),
        france_travail_provider(),
        quota=settings.ai_daily_quota_per_user,
    )
