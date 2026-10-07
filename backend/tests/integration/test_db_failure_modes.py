"""How the DB layer behaves when things go wrong (timeouts, exhaustion, dead connections)."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from recruitai.config import Settings
from recruitai.core.db import create_engine


@pytest.fixture
def make_engine(test_database_url, monkeypatch):
    def _make(**env: str) -> AsyncEngine:
        monkeypatch.setenv("ENV", "local")
        monkeypatch.setenv(
            "DATABASE_URL", test_database_url.render_as_string(hide_password=False)
        )
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        engine = create_engine(Settings(_env_file=None))
        return engine

    return _make


async def test_statement_timeout_cancels_slow_query(make_engine):
    engine = make_engine(DB_STATEMENT_TIMEOUT_MS="200")
    try:
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(text("SELECT pg_sleep(3)"))
    finally:
        await engine.dispose()


async def test_idle_in_transaction_session_is_terminated(make_engine):
    engine = make_engine(DB_IDLE_IN_TRANSACTION_TIMEOUT_MS="300")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("SELECT 1")
            )  # opens a transaction and leaves it idle
            await asyncio.sleep(1.0)
            with pytest.raises(DBAPIError):
                await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def test_pool_exhaustion_fails_fast_instead_of_hanging(make_engine):
    engine = make_engine(DB_POOL_SIZE="1", DB_MAX_OVERFLOW="0", DB_POOL_TIMEOUT_S="1")
    try:
        async with engine.connect():
            with pytest.raises(PoolTimeoutError):
                # Outer bound so a broken pool_timeout fails the test instead of hanging CI.
                async with asyncio.timeout(10), engine.connect():
                    pass
    finally:
        await engine.dispose()


async def test_pool_recovers_after_its_connection_was_killed(make_engine):
    """pool_pre_ping: a dead pooled connection is replaced, not surfaced as a 500."""
    engine = make_engine(DB_POOL_SIZE="1", DB_MAX_OVERFLOW="0")
    try:
        async with engine.connect() as conn:
            pid = (await conn.execute(text("SELECT pg_backend_pid()"))).scalar()
        killer = make_engine()
        async with killer.connect() as k:
            await k.execute(text("SELECT pg_terminate_backend(:p)"), {"p": pid})
        await killer.dispose()

        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT 1"))).scalar() == 1
    finally:
        await engine.dispose()
