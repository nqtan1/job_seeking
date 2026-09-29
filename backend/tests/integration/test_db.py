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


async def test_get_db_select_one_round_trips(initialised_db):
    gen = get_db()
    session = await anext(gen)

    assert isinstance(session, AsyncSession)
    assert (await session.execute(text("SELECT 1"))).scalar() == 1
    await gen.aclose()


async def _finish(gen) -> None:
    """Complete the dependency the way FastAPI does on a successful request."""
    with pytest.raises(StopAsyncIteration):
        await anext(gen)


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


async def _rows() -> int:
    async with core_db._session_factory() as s:  # type: ignore[misc]
        return (await s.execute(text("SELECT count(*) FROM t_get_db_probe"))).scalar()


async def test_get_db_does_not_commit_on_success(probe_table):
    gen = get_db()
    session = await anext(gen)
    await session.execute(text("INSERT INTO t_get_db_probe VALUES (1)"))
    await _finish(gen)  # request finished OK: still nothing committed

    assert await _rows() == 0


async def test_get_db_keeps_writes_the_service_committed(probe_table):
    gen = get_db()
    session = await anext(gen)
    await session.execute(text("INSERT INTO t_get_db_probe VALUES (1)"))
    await session.commit()
    await _finish(gen)

    assert await _rows() == 1


async def test_get_db_rolls_back_when_the_request_fails(probe_table):
    gen = get_db()
    session = await anext(gen)
    await session.execute(text("INSERT INTO t_get_db_probe VALUES (1)"))
    with pytest.raises(ValueError):
        await gen.athrow(ValueError("handler failed"))

    assert await _rows() == 0


async def test_engine_uses_psycopg_and_sets_timeouts(test_database_url, monkeypatch):
    engine: AsyncEngine = create_engine(
        _settings(
            monkeypatch,
            test_database_url.render_as_string(hide_password=False),
            DB_STATEMENT_TIMEOUT_MS="1234",
        )
    )
    try:
        assert engine.dialect.driver == "psycopg"
        async with engine.connect() as conn:
            assert (
                await conn.execute(text("SHOW statement_timeout"))
            ).scalar() == "1234ms"
            app_name = (await conn.execute(text("SHOW application_name"))).scalar()
            assert app_name == "recruitai-api"
    finally:
        await engine.dispose()


def test_plain_postgresql_url_is_upgraded_to_psycopg(monkeypatch):
    engine = create_engine(_settings(monkeypatch, "postgresql://u:p@localhost/x_test"))

    assert engine.dialect.driver == "psycopg"


def test_non_psycopg_driver_is_rejected(monkeypatch):
    with pytest.raises(ValueError):
        create_engine(
            _settings(monkeypatch, "postgresql+asyncpg://u:p@localhost/x_test")
        )


def test_base_has_naming_convention():
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"


async def test_get_db_without_init_raises():
    await core_db.close_db()
    gen = get_db()

    with pytest.raises(RuntimeError):
        await anext(gen)
