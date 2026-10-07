"""Async SQLAlchemy engine, declarative ``Base`` and the per-request session dependency.

Transactions are explicit: ``get_db()`` never commits. A service that wants its writes
kept calls ``await session.commit()``; anything else is rolled back when the session
closes. This keeps "business write + task enqueue" boundaries visible in the service.
"""

from collections.abc import AsyncIterator

from sqlalchemy import MetaData, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from recruitai.config import Settings

# Deterministic constraint names keep Alembic autogenerate and later migrations stable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine(
    settings: Settings, *, application_name: str = "recruitai-api"
) -> AsyncEngine:
    """Build the engine on the psycopg (v3) async driver (ADR 0017)."""
    url = make_url(settings.database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError(
            "DATABASE_URL must use the psycopg driver (postgresql+psycopg://)"
        )
    options = (
        f"-c statement_timeout={settings.db_statement_timeout_ms} "
        f"-c idle_in_transaction_session_timeout={settings.db_idle_in_transaction_timeout_ms}"
    )
    return create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_recycle=settings.db_pool_recycle_s,
        pool_pre_ping=True,
        connect_args={"options": options, "application_name": application_name},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(settings: Settings) -> None:
    """Create the process-wide engine. Called from the app lifespan, not at import."""
    global _engine, _session_factory
    _engine = create_engine(settings)
    _session_factory = create_session_factory(_engine)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncIterator[AsyncSession]:
    """Session-per-request dependency. Does not commit; see the module docstring."""
    if _session_factory is None:
        raise RuntimeError("database not initialised (init_db was not called)")
    async with _session_factory() as session:
        yield session


async def count_rows(session: AsyncSession, model: type[Base]) -> int:
    """Row count of a whole table, for platform statistics (admin only, never per tenant)."""
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()
