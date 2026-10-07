"""Database fixtures. One strategy: TEST_DATABASE_URL (compose Postgres locally, a service
container in CI). Each test runs in a transaction that is rolled back at teardown, even if
the code under test calls ``commit()`` (SAVEPOINT join mode)."""

import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

DEFAULT_TEST_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/recruitai_test"
)


def _test_url() -> URL:
    url = make_url(os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_URL))
    name = url.database or ""
    if "test" not in name:
        raise RuntimeError(
            f"refusing to run tests on database {name!r}: name must contain 'test'"
        )
    return url


@pytest.fixture(scope="session")
def test_database_url() -> URL:
    """Validated test URL; creates the database if it does not exist yet."""
    url = _test_url()
    admin = url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(
        admin.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (url.database,)
        )
        if exists.fetchone() is None:
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database or ""))
            )
    return url


@pytest.fixture
async def db_engine(migrated_test_db: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_test_db, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


async def purge_tenant(engine: AsyncEngine, *, org_id: object, user_id: object) -> None:
    """Delete a tenant a test committed for real (concurrency tests can't use the rolled-back
    ``db_session``). Other tests count rows globally, so leftovers would break them."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM organizations WHERE id = :o"), {"o": org_id}
        )
        await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
