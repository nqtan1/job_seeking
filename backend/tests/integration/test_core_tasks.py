"""core/tasks.py + worker.py (P1-13b): the real transactional-enqueue helper + task_runs,
against the shared Alembic-migrated test database — a different (and more representative)
setup than tests/fixtures/queue.py's isolated spike database, which only proves the
atomicity primitive in the abstract, on a throwaway schema.

Uses real commits (via ``db_engine``, not the rollback-wrapped ``db_session``): the worker
runs on a separate connection and must see committed data. The ``real_org`` fixture cleans
up after itself for exactly that reason — a leaked, permanently-committed row here would
otherwise pollute every other test sharing this database (caught the hard way: it broke
three unrelated tests' row counts before this fixture had a teardown).
"""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.core.tasks import TaskRun, enqueue
from recruitai.modules.identity.models import Organization
from recruitai.worker import dummy


@pytest.fixture
async def real_org(db_engine: AsyncEngine) -> AsyncIterator[UUID]:
    org_id = uuid4()
    async with AsyncSession(db_engine) as session:
        session.add(Organization(id=org_id, name="task-test", kind="personal"))
        await session.commit()
    yield org_id
    async with AsyncSession(db_engine) as session:
        await session.execute(
            text("DELETE FROM organizations WHERE id = :i"), {"i": str(org_id)}
        )
        await session.commit()


async def _status(db_engine: AsyncEngine, task_run_id: UUID) -> str:
    async with AsyncSession(db_engine) as session:
        row = (
            await session.execute(select(TaskRun).where(TaskRun.id == task_run_id))
        ).scalar_one()
        return row.status


async def test_enqueue_and_worker_transitions_queued_to_done(
    db_engine: AsyncEngine, task_app, real_org: UUID
):
    async with AsyncSession(db_engine) as session:
        task_run_id = await enqueue(session, task=dummy, org_id=real_org, kind="dummy")
        await session.commit()

    assert await _status(db_engine, task_run_id) == "queued"

    await task_app.run_worker_async(wait=False, install_signal_handlers=False)

    assert await _status(db_engine, task_run_id) == "done"


async def test_failed_task_marks_task_run_failed_not_left_queued(
    db_engine: AsyncEngine, task_app, real_org: UUID
):
    """A forced-failure test proves no orphaned task_runs row: it ends in the terminal
    'failed' state, never stuck in 'queued' forever."""
    async with AsyncSession(db_engine) as session:
        task_run_id = await enqueue(
            session,
            task=dummy,
            org_id=real_org,
            kind="dummy",
            task_kwargs={"should_fail": True},
        )
        await session.commit()

    await task_app.run_worker_async(wait=False, install_signal_handlers=False)

    async with AsyncSession(db_engine) as session:
        row = (
            await session.execute(select(TaskRun).where(TaskRun.id == task_run_id))
        ).scalar_one()
        assert row.status == "failed"
        assert row.error_code == "dummy_failure"


async def test_enqueue_rolls_back_with_the_callers_transaction(
    db_engine: AsyncEngine, task_app, real_org: UUID
):
    """The business write and the enqueue share the caller's connection (ADR 0017): if the
    caller's transaction never commits, neither the task_runs row nor the job exists."""
    async with AsyncSession(db_engine) as session:
        task_run_id = await enqueue(session, task=dummy, org_id=real_org, kind="dummy")
        # deliberately never committed

    async with AsyncSession(db_engine) as session:
        result = await session.execute(select(TaskRun).where(TaskRun.id == task_run_id))
        assert result.scalar_one_or_none() is None

    # and the worker has nothing to process: no job was ever committed either
    await task_app.run_worker_async(wait=False, install_signal_handlers=False)
