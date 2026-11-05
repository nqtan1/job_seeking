"""``agents:run_flow``: one run of one flow (ADR 0031). Not retried automatically: a blind retry only
spends more AI calls, so a failed run waits for the user's Resume. The engine is idempotent anyway."""

import logging
from uuid import UUID

import procrastinate
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import AppError
from recruitai.core.tasks import mark_done, mark_failed
from recruitai.modules.agents.flows import engine

logger = logging.getLogger(__name__)

blueprint = procrastinate.Blueprint()


async def _unstick(
    session: "AsyncSession", org_id: str, run_id: str, code: str
) -> None:
    """A task that dies before the engine starts must not leave its run queued forever."""
    from recruitai.modules.agents.flows import repository as repo

    await session.rollback()
    await repo.fail_active_run(
        session, org_id=UUID(org_id), run_id=UUID(run_id), code=code
    )
    await session.commit()


@blueprint.periodic(cron="*/10 * * * *")
@blueprint.task(name="fail_stale_runs")
async def fail_stale_runs(timestamp: int) -> None:
    from datetime import UTC, datetime

    from recruitai.config import get_settings
    from recruitai.modules.agents.flows import runs as flow_runs
    from recruitai.worker import session_factory

    async with session_factory() as session:
        await flow_runs.fail_stale_runs(
            session,
            now=datetime.now(UTC),
            abandoned_after=flow_runs.abandoned_after(get_settings()),
        )


@blueprint.periodic(cron="*/5 * * * *")
@blueprint.task(name="run_due_schedules")
async def run_due_schedules(timestamp: int) -> None:
    from datetime import UTC, datetime

    from recruitai.config import get_settings
    from recruitai.modules.agents.flows import schedules
    from recruitai.worker import session_factory

    if not get_settings().helpers_enabled:
        return  # the feature is off: nothing starts by itself
    async with session_factory() as session:
        await schedules.run_due(session, now=datetime.now(UTC))


@blueprint.periodic(cron="* * * * *")
@blueprint.task(name="poll_telegram")
async def poll_telegram(timestamp: int) -> None:
    """Finish the Telegram links people started (ADR 0036). Nothing happens without a bot."""
    from datetime import UTC, datetime

    from recruitai.config import get_settings
    from recruitai.core.telegram import get_telegram
    from recruitai.modules.agents.connections import service as connections
    from recruitai.worker import session_factory

    settings = get_settings()
    bot = get_telegram(settings)
    if bot is None or not settings.helpers_enabled:
        return
    async with session_factory() as session:
        await connections.poll_telegram(session, bot, now=datetime.now(UTC))


@blueprint.task(name="run_flow")
async def run_flow(task_run_id: str, org_id: str, user_id: str, run_id: str) -> None:
    from recruitai.ai.dependencies import build_llm_gateway
    from recruitai.ai.overrides import effective_settings
    from recruitai.config import get_settings
    from recruitai.worker import session_factory

    settings = get_settings()
    task_id = UUID(task_run_id)
    async with session_factory() as session:
        try:
            llm = build_llm_gateway(
                await effective_settings(settings, session),
                session,
                org_id=UUID(org_id),
                user_id=UUID(user_id),
            )
            await engine.execute(session, llm, org_id=UUID(org_id), run_id=UUID(run_id))
        except AppError as exc:
            await _unstick(session, org_id, run_id, exc.code)
            await mark_failed(session, task_id, error_code=exc.code)
            return
        except Exception as exc:  # noqa: BLE001  (a safe code, never exception text)
            logger.error("flow task failed", extra={"error_type": type(exc).__name__})
            await _unstick(session, org_id, run_id, "flow_failed")
            await mark_failed(session, task_id, error_code="flow_failed")
            return
        await mark_done(session, task_id, result_ref=run_id)
