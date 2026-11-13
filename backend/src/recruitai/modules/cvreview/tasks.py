"""``cvreview:evaluate``: one smart model call, grounded in code (docs/design/cv-review-technical.md).
Retries transient failures; the row exists only on success, ``task_runs`` holds the failure code."""

import logging
from uuid import UUID

import procrastinate
from procrastinate import JobContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import AppError
from recruitai.core.tasks import mark_done, mark_failed
from recruitai.modules.cvreview import service

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
MODEL_TIMEOUT_S = (
    240  # a 150-block CV answers with 150 comments: slower than the 120 s default
)

blueprint = procrastinate.Blueprint()


async def _drop_blocks(session: AsyncSession, context: JobContext) -> None:
    """Edited CV text sits in the job args only while the job can still retry (privacy)."""
    await session.execute(
        text("UPDATE procrastinate_jobs SET args = args - 'blocks' WHERE id = :id"),
        {"id": context.job.id},
    )


@blueprint.task(
    name="evaluate",
    pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=MAX_ATTEMPTS, exponential_wait=5),
)
async def evaluate(
    context: JobContext,
    task_run_id: str,
    org_id: str,
    user_id: str,
    document_id: str | None,
    parent_id: str | None,
    track: str,
    level: str,
    blocks: list[dict[str, str]]
    | None = None,  # dropped from the job args once the job is final
) -> None:
    from recruitai.ai.dependencies import build_llm_gateway
    from recruitai.ai.overrides import effective_settings
    from recruitai.config import get_settings
    from recruitai.modules.identity import service as identity
    from recruitai.worker import (  # the worker owns the resources
        session_factory,
        storage,
    )

    run_id, org, user = UUID(task_run_id), UUID(org_id), UUID(user_id)
    parent = UUID(parent_id) if parent_id else None
    async with session_factory() as session:
        try:
            source = await service.load_source(
                session,
                storage,
                org_id=org,
                document_id=UUID(document_id) if document_id else None,
                parent_id=parent,
                blocks=blocks,
            )
            llm = build_llm_gateway(
                (await effective_settings(get_settings(), session)).model_copy(
                    update={"ai_call_timeout_s": MODEL_TIMEOUT_S}
                ),
                session,
                org_id=org,
                user_id=user,
            )
            row = await service.evaluate(
                session,
                llm,
                org_id=org,
                language=await identity.user_language(session, user),
                track=track,
                level=level,
                source=source,
                parent_id=parent,
            )
            await _drop_blocks(session, context)
            await mark_done(session, run_id, result_ref=str(row.id))
            return
        except Exception as exc:  # noqa: BLE001  (anything becomes a safe code below)
            await session.rollback()
            app = exc if isinstance(exc, AppError) else None
            code = app.code if app else "cv_review_failed"
            # a 503 may pass on retry; a timeout will not (same CV, same model, 3x the cost)
            retryable = app is None or (
                app.status_code >= 500 and app.code != "ai_timeout"
            )
            # The type only: a message could contain CV text (never logged).
            logger.error("cvreview failed", extra={"error_type": type(exc).__name__, "task_run_id": task_run_id})  # fmt: skip
        if retryable and context.job.attempts + 1 < MAX_ATTEMPTS:
            raise RuntimeError(code)  # Procrastinate retries with backoff
        await _drop_blocks(session, context)
        await mark_failed(session, run_id, error_code=code)
