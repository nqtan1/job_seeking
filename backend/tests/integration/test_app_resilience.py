import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from recruitai.core import db as core_db
from recruitai.core.db import get_db
from recruitai.main import create_app


@pytest.fixture
def app_with_dead_db() -> FastAPI:
    """DB unreachable (nothing listens on port 1). Also proves nothing leaks its error."""
    app = create_app()
    engine = create_async_engine(
        "postgresql+psycopg://user:secretpw@127.0.0.1:1/nope",
        poolclass=NullPool,
        connect_args={"connect_timeout": 2},
    )

    async def _db():
        async with AsyncSession(engine) as s:
            yield s

    app.dependency_overrides[get_db] = _db
    return app


async def test_dead_database_makes_ready_503_without_leaks_but_health_stays_up(
    app_with_dead_db: FastAPI,
):
    transport = httpx.ASGITransport(app=app_with_dead_db)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        ready = await c.get("/ready")
        health = await c.get("/health")

    assert ready.status_code == 503 and ready.json() == {"status": "unavailable"}
    for secret in ("secretpw", "127.0.0.1", "psycopg", "Traceback"):
        assert secret not in ready.text
    assert health.status_code == 200


def test_engine_is_created_by_the_lifespan_not_at_import_and_disposed_after():
    assert core_db._engine is None  # importing/creating the app opens nothing

    with TestClient(create_app()) as client:
        assert core_db._engine is not None
        assert client.get("/ready").json() == {"status": "ready"}

    assert core_db._engine is None and core_db._session_factory is None


async def test_db_session_writes_are_invisible_to_other_connections(
    db_session: AsyncSession, db_engine
):
    """Order-independent proof that the fixture never commits for real: while the test is
    running, a separate connection must not see the row, even after the code called commit()."""
    marker = uuid.uuid4().int % 1_000_000_000
    async with db_engine.connect() as admin:
        await admin.execute(text("CREATE TABLE IF NOT EXISTS bleed_probe (n bigint)"))
        await admin.commit()
    await db_session.execute(text("INSERT INTO bleed_probe VALUES (:n)"), {"n": marker})
    await db_session.commit()

    async with db_engine.connect() as other:
        seen = (
            await other.execute(
                text("SELECT count(*) FROM bleed_probe WHERE n = :n"), {"n": marker}
            )
        ).scalar()
    assert seen == 0
