"""core/tasks.py fixtures.

Uses ``recruitai.worker.app`` itself: the task registry is per App instance, so another App
cannot find the deferred task. Procrastinate's schema lives in the shared migrated test DB
(ADR 0017), unlike tests/fixtures/queue.py's isolated database.
"""

from collections.abc import AsyncIterator

import procrastinate
import pytest
from sqlalchemy.engine import URL

from recruitai.worker import app as worker_app


@pytest.fixture(scope="session")
async def task_app(migrated_test_db: URL) -> AsyncIterator[procrastinate.App]:
    async with worker_app.open_async():
        await worker_app.schema_manager.apply_schema_async()
        yield worker_app
