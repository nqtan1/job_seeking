"""core/tasks.py (P1-13b) fixtures.

Uses ``recruitai.worker.app`` directly — the *same* App instance that has ``dummy``
registered — rather than a freshly-constructed one: Procrastinate's task registry is
per-App-instance, so a worker running on a different App object can never find a task
deferred against this one (``TaskNotFound``, caught the hard way writing this fixture).

Procrastinate's own schema is applied to the same shared, Alembic-migrated test database
``task_runs`` lives in — matching production's single-database topology (ADR 0017 needs one
connection to span both the business write and the enqueue). This is deliberately a
different database than the P1-13 spike's isolated ``recruitai_test_queue`` (see
tests/fixtures/queue.py), which exists only to prove the atomicity primitive in the abstract.
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
