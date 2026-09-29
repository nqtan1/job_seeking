import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.config import Settings
from recruitai.core import db as core_db
from recruitai.core.db import Base, create_engine, get_db

PG_DB = "postgresql+psycopg://postgres:postgres@localhost:5432/recruitai_test"


def _settings(monkeypatch, url: str, **extra: str) -> Settings:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DATABASE_URL", url)
    for k, v in extra.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)


@pytest.fixture
async def initialised_db(test_database_url, monkeypatch):
    core_db.init_db(
        _settings(monkeypatch, test_database_url.render_as_string(hide_password=False))
    )
    yield
    await core_db.close_db()


async def _finish(gen) -> None:
    """Complete the dependency the way FastAPI does on a successful request."""
    with pytest.raises(StopAsyncIteration):
        await anext(gen)


async def _rows() -> int:
    async with core_db._session_factory() as s:  # type: ignore[misc]
        return (await s.execute(text("SELECT count(*) FROM t_get_db_probe"))).scalar()


@pytest.fixture
async def probe_table(initialised_db):
    async with core_db._session_factory() as s:  # type: ignore[misc]
        await s.execute(text("CREATE TABLE IF NOT EXISTS t_get_db_probe (n int)"))
        await s.execute(text("TRUNCATE t_get_db_probe"))
        await s.commit()
    yield
    async with core_db._session_factory() as s:  # type: ignore[misc]
        await s.execute(text("DROP TABLE t_get_db_probe"))
        await s.commit()


async def test_get_db_transaction_semantics(probe_table):
    insert = text("INSERT INTO t_get_db_probe VALUES (1)")

    gen = get_db()  # works, and hands out a real session
    session = await anext(gen)
    assert isinstance(session, AsyncSession)
    assert (await session.execute(text("SELECT 1"))).scalar() == 1
    await session.execute(insert)
    await _finish(gen)  # request finished OK, but nobody committed: nothing is kept
    assert await _rows() == 0

    gen = get_db()  # a service that commits keeps its writes
    session = await anext(gen)
    await session.execute(insert)
    await session.commit()
    await _finish(gen)
    assert await _rows() == 1

    gen = get_db()  # a failing request rolls back
    session = await anext(gen)
    await session.execute(insert)
    with pytest.raises(ValueError):
        await gen.athrow(ValueError("handler failed"))
    assert await _rows() == 1  # still only the committed row


async def test_engine_config_psycopg_timeouts_url_handling_and_naming(
    test_database_url, monkeypatch
):
    url = test_database_url.render_as_string(hide_password=False)
    engine: AsyncEngine = create_engine(
        _settings(monkeypatch, url, DB_STATEMENT_TIMEOUT_MS="1234")
    )
    try:
        assert engine.dialect.driver == "psycopg"
        async with engine.connect() as conn:
            assert (
                await conn.execute(text("SHOW statement_timeout"))
            ).scalar() == "1234ms"
            assert (
                await conn.execute(text("SHOW application_name"))
            ).scalar() == "recruitai-api"
    finally:
        await engine.dispose()

    plain = create_engine(_settings(monkeypatch, "postgresql://u:p@localhost/x_test"))
    assert plain.dialect.driver == "psycopg"  # a plain postgresql:// URL is upgraded
    with pytest.raises(ValueError):
        create_engine(
            _settings(monkeypatch, "postgresql+asyncpg://u:p@localhost/x_test")
        )
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"


async def test_get_db_without_init_raises():
    await core_db.close_db()

    with pytest.raises(RuntimeError):
        await anext(get_db())
