"""Procrastinate worker entrypoint: ``uv run procrastinate --app=recruitai.worker.app worker``.

Procrastinate's own schema is separate from Alembic (see core/tasks.py) and must be applied
once before the worker can run: ``uv run procrastinate --app=recruitai.worker.app schema
--apply``.
"""

from uuid import UUID

from recruitai.config import get_settings
from recruitai.core.db import create_engine, create_session_factory
from recruitai.core.logging import configure_logging
from recruitai.core.storage import get_storage
from recruitai.core.tasks import build_app, mark_done, mark_failed
from recruitai.modules.identity import tasks as identity_tasks
from recruitai.modules.letters import tasks as letters_tasks
from recruitai.modules.privacy import tasks as privacy_tasks
from recruitai.modules.radar import tasks as radar_tasks

settings = get_settings()
configure_logging(
    settings.log_level
)  # JSON, and httpx/urllib3 URLs (query strings) stay quiet
app = build_app(settings)

_engine = create_engine(settings, application_name="recruitai-worker")
session_factory = create_session_factory(_engine)
storage = get_storage(settings)

# Module tasks are defined on blueprints and registered here, under the module's namespace.
app.add_tasks_from(letters_tasks.blueprint, namespace="letters")
app.add_tasks_from(privacy_tasks.blueprint, namespace="privacy")
app.add_tasks_from(identity_tasks.blueprint, namespace="identity")
app.add_tasks_from(radar_tasks.blueprint, namespace="radar")
# Bound to ``app`` now: these are the Task objects API code enqueues.
render_pdf = letters_tasks.render_pdf
export_user_data = privacy_tasks.export_user_data


@app.task(name="core.tasks.dummy")
async def dummy(task_run_id: str, should_fail: bool = False) -> None:
    """Proves the enqueue -> worker -> task_runs pattern end to end (P1 exit criteria,
    P1-13b). Not used by any real feature — those tasks land per-module from P2 on."""
    async with session_factory() as session:
        if should_fail:
            await mark_failed(session, UUID(task_run_id), error_code="dummy_failure")
            raise RuntimeError("simulated dummy task failure")
        await mark_done(session, UUID(task_run_id))
