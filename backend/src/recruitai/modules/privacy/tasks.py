"""``privacy:export_user_data``: build the caller's data-export ZIP in the worker.

Same failure convention as ``letters:render_pdf``: 3 attempts with backoff for anything
unexpected, then ``task_runs.status='failed'`` with a safe ``error_code`` (never exception
text, which could contain user data)."""

import logging
from datetime import UTC, datetime
from uuid import UUID

import procrastinate
from procrastinate import JobContext

from recruitai.core.tasks import mark_done, mark_failed
from recruitai.modules.privacy import service

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3

blueprint = procrastinate.Blueprint()


@blueprint.task(
    name="export_user_data",
    pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=MAX_ATTEMPTS, exponential_wait=10),
)
async def export_user_data(
    context: JobContext, task_run_id: str, org_id: str, user_id: str
) -> None:
    from recruitai.worker import (  # the worker owns the resources
        session_factory,
        storage,
    )

    run_id = UUID(task_run_id)
    async with session_factory() as session:
        try:
            document_id = await service.build_export(
                session, storage, org_id=UUID(org_id), user_id=UUID(user_id)
            )
            await session.commit()
            await mark_done(session, run_id, result_ref=str(document_id))
            return
        except Exception as exc:  # noqa: BLE001  (unexpected: becomes a safe code below)
            await session.rollback()
            logger.error(
                "export failed",
                extra={"error_type": type(exc).__name__, "task_run_id": task_run_id},
            )
        if context.job.attempts + 1 < MAX_ATTEMPTS:
            raise RuntimeError("export_failed")  # Procrastinate retries with backoff
        await mark_failed(session, run_id, error_code="export_failed")


# ---- Scheduled retention sweeps (ARCHITECTURE.md §11.2). Idempotent, so a missed or doubled
# run is harmless; no task_runs row (nobody polls housekeeping). Failures are logged by type
# only and retried at the next cron tick.


def _now() -> datetime:
    return datetime.now(UTC)


@blueprint.periodic(cron="5 * * * *")
@blueprint.task(name="sweep_job_search_cache")
async def sweep_job_search_cache(timestamp: int) -> None:
    from recruitai.worker import session_factory

    async with session_factory() as session:
        await service.sweep_job_search_cache(session, now=_now())


@blueprint.periodic(cron="20 * * * *")
@blueprint.task(name="sweep_exports")
async def sweep_exports(timestamp: int) -> None:
    from recruitai.worker import session_factory, storage

    async with session_factory() as session:
        await service.sweep_exports(session, storage, now=_now())


@blueprint.periodic(cron="30 3 * * *")
@blueprint.task(name="sweep_ai_calls")
async def sweep_ai_calls(timestamp: int) -> None:
    from recruitai.worker import session_factory

    async with session_factory() as session:
        await service.sweep_ai_calls(session, now=_now())


@blueprint.periodic(cron="40 3 * * *")
@blueprint.task(name="sweep_radar_runs")
async def sweep_radar_runs(timestamp: int) -> None:
    from recruitai.worker import session_factory

    async with session_factory() as session:
        await service.sweep_radar_runs(session, now=_now())


@blueprint.periodic(cron="0 4 * * *")
@blueprint.task(name="sweep_inactive_accounts")
async def sweep_inactive_accounts(timestamp: int) -> None:
    from firebase_admin import auth as firebase_auth

    from recruitai.config import get_settings
    from recruitai.core.auth import get_firebase_app
    from recruitai.core.email import get_email_sender
    from recruitai.worker import session_factory, storage

    settings = get_settings()
    app = get_firebase_app(settings)

    def delete_identity_for(firebase_uid: str):  # type: ignore[no-untyped-def]
        async def delete() -> None:
            from starlette.concurrency import run_in_threadpool

            try:
                await run_in_threadpool(
                    firebase_auth.delete_user, firebase_uid, app=app
                )
            except firebase_auth.UserNotFoundError:
                return

        return delete

    async with session_factory() as session:
        await service.sweep_inactive_accounts(
            session,
            storage,
            get_email_sender(settings),
            now=_now(),
            delete_identity_for=delete_identity_for,
        )
