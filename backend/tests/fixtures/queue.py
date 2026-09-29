"""Procrastinate fixtures for the transactional-enqueue contract (ADR 0017).

Uses its own database (``recruitai_test_queue``) because Procrastinate owns its schema and
that must not interfere with the Alembic-managed test database. Recreated once per session.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import procrastinate
import psycopg
import pytest
from procrastinate import PsycopgConnector
from procrastinate.tasks import Task
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

QUEUE_DB = "recruitai_test_queue"


@dataclass
class Queue:
    app: procrastinate.App
    task: Task  # type: ignore[type-arg]
    dsn: str
    processed: list[str] = field(default_factory=list)

    # --- what a *different* connection (any other process) sees ---
    def _count(self, query: str, *args: str) -> int:
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(query, args).fetchone()
            assert row is not None
            return int(row[0])

    def business(self, label: str) -> int:
        return self._count(
            "SELECT count(*) FROM queue_business WHERE label = %s", label
        )

    def jobs(self, label: str) -> int:
        return self._count(
            "SELECT count(*) FROM procrastinate_jobs WHERE args->>'label' = %s", label
        )

    def succeeded(self, label: str) -> int:
        return self._count(
            "SELECT count(*) FROM procrastinate_jobs WHERE args->>'label' = %s AND status = 'succeeded'",
            label,
        )

    async def enqueue_in_session(self, session: AsyncSession, label: str) -> None:
        """The contract under test: business write + enqueue on the SESSION's connection."""
        await session.execute(
            text("INSERT INTO queue_business(label) VALUES (:l)"), {"l": label}
        )
        conn = await session.connection()
        raw = (await conn.get_raw_connection()).driver_connection
        await self.task.configure(connection=raw).defer_async(label=label)

    async def enqueue_on_separate_connection(
        self, session: AsyncSession, label: str
    ) -> None:
        """Deliberately WRONG (what asyncpg + a separate pool would do). Used only to prove
        the tests can detect a broken implementation."""
        await session.execute(
            text("INSERT INTO queue_business(label) VALUES (:l)"), {"l": label}
        )
        await self.task.defer_async(label=label)

    async def run_worker(self) -> None:
        await self.app.run_worker_async(wait=False, install_signal_handlers=False)


@pytest.fixture(scope="session")
def queue_url(test_database_url: URL) -> URL:
    admin = test_database_url.set(drivername="postgresql", database="postgres")
    target = test_database_url.set(drivername="postgresql", database=QUEUE_DB)
    with psycopg.connect(
        admin.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(QUEUE_DB)
            )
        )
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(QUEUE_DB)))

    async def _apply_schema() -> None:
        app = procrastinate.App(
            connector=PsycopgConnector(
                conninfo=target.render_as_string(hide_password=False)
            )
        )
        async with app.open_async():
            await app.schema_manager.apply_schema_async()

    asyncio.run(_apply_schema())
    with psycopg.connect(
        target.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        conn.execute(
            "CREATE TABLE queue_business (id serial PRIMARY KEY, label text NOT NULL)"
        )
    return target


@pytest.fixture
async def queue(queue_url: URL) -> AsyncIterator[Queue]:
    dsn = queue_url.render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE procrastinate_jobs, queue_business RESTART IDENTITY CASCADE"
        )

    app = procrastinate.App(connector=PsycopgConnector(conninfo=dsn))
    holder: dict[str, Queue] = {}

    @app.task(name="tests.queue.dummy")
    async def dummy(label: str) -> None:
        holder["q"].processed.append(label)

    q = Queue(app=app, task=dummy, dsn=dsn)
    holder["q"] = q
    async with app.open_async():
        yield q


@pytest.fixture
async def queue_engine(queue_url: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        queue_url.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    yield engine
    await engine.dispose()
