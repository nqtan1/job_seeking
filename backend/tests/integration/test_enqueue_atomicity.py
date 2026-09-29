"""Permanent regression tests for ADR 0017: business write + task enqueue are one transaction.

If any of these fail, do not "fix the test": a change in our DB layer, the driver, or
Procrastinate has broken the no-lost-job / no-orphan-job guarantee.
"""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.fixtures.queue import Queue


async def test_commit_persists_business_row_and_job(
    queue: Queue, queue_engine: AsyncEngine
):
    async with AsyncSession(queue_engine) as s:
        await queue.enqueue_in_session(s, "commit")
        # Not visible to anyone else before commit...
        assert (queue.business("commit"), queue.jobs("commit")) == (0, 0)
        await s.commit()

    assert (queue.business("commit"), queue.jobs("commit")) == (1, 1)


async def test_rollback_leaves_neither(queue: Queue, queue_engine: AsyncEngine):
    async with AsyncSession(queue_engine) as s:
        await queue.enqueue_in_session(s, "rollback")
        await s.rollback()

    assert (queue.business("rollback"), queue.jobs("rollback")) == (0, 0)


async def test_exception_inside_transaction_leaves_neither(
    queue: Queue, queue_engine: AsyncEngine
):
    async with AsyncSession(queue_engine) as s:
        with pytest.raises(RuntimeError):
            async with s.begin():
                await queue.enqueue_in_session(s, "boom")
                raise RuntimeError("failure after enqueue")

    assert (queue.business("boom"), queue.jobs("boom")) == (0, 0)


async def test_closing_session_without_commit_leaves_neither(
    queue: Queue, queue_engine: AsyncEngine
):
    # get_db() never commits: a service that forgets to commit must not leave a job behind.
    async with AsyncSession(queue_engine) as s:
        await queue.enqueue_in_session(s, "no-commit")

    assert (queue.business("no-commit"), queue.jobs("no-commit")) == (0, 0)


async def test_savepoint_joined_session_leaves_nothing_after_outer_rollback(
    queue: Queue, queue_engine: AsyncEngine
):
    # The shape of the `db_session` test fixture.
    async with queue_engine.connect() as conn:
        outer = await conn.begin()
        s = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        await queue.enqueue_in_session(s, "savepoint")
        await s.commit()  # savepoint only
        await s.close()
        await outer.rollback()

    assert (queue.business("savepoint"), queue.jobs("savepoint")) == (0, 0)


async def test_backend_killed_mid_transaction_leaves_neither(
    queue: Queue, queue_engine: AsyncEngine
):
    """Crash simulation: the connection dies after the enqueue and before the commit."""
    async with AsyncSession(queue_engine) as s:
        await queue.enqueue_in_session(s, "crash")
        pid = (await s.execute(text("SELECT pg_backend_pid()"))).scalar()
        async with queue_engine.connect() as killer:
            await killer.execute(text("SELECT pg_terminate_backend(:p)"), {"p": pid})
        with pytest.raises(Exception):  # noqa: B017 - driver error type is not the point
            await s.commit()

    assert (queue.business("crash"), queue.jobs("crash")) == (0, 0)


async def test_concurrent_sessions_only_committed_work_has_jobs(
    queue: Queue, queue_engine: AsyncEngine
):
    """20 concurrent transactions, half commit and half roll back: no orphans, none lost."""

    async def one(i: int) -> None:
        async with AsyncSession(queue_engine) as s:
            await queue.enqueue_in_session(s, f"c{i}")
            await asyncio.sleep(0.01 * (i % 5))  # interleave the transactions
            if i % 2 == 0:
                await s.commit()
            else:
                await s.rollback()

    await asyncio.gather(*(one(i) for i in range(20)))

    for i in range(20):
        expected = 1 if i % 2 == 0 else 0
        assert (queue.business(f"c{i}"), queue.jobs(f"c{i}")) == (expected, expected), i


async def test_committed_job_runs_exactly_once_and_rolled_back_never_runs(
    queue: Queue, queue_engine: AsyncEngine
):
    async with AsyncSession(queue_engine) as s:
        await queue.enqueue_in_session(s, "kept")
        await s.commit()
    async with AsyncSession(queue_engine) as s:
        await queue.enqueue_in_session(s, "dropped")
        await s.rollback()

    await queue.run_worker()
    await queue.run_worker()  # a second pass must not re-run it

    assert queue.processed == ["kept"]
    assert queue.succeeded("kept") == 1


async def test_detector_catches_a_separate_connection_enqueue(
    queue: Queue, queue_engine: AsyncEngine
):
    """Guards the guard: the wrong implementation MUST make these assertions fail, otherwise
    the tests above could pass for the wrong reason."""
    async with AsyncSession(queue_engine) as s:
        await queue.enqueue_on_separate_connection(s, "wrong")
        await s.rollback()

    assert (queue.business("wrong"), queue.jobs("wrong")) == (0, 1)  # orphan job
