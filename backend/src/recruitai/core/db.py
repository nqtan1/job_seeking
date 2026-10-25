"""Async SQLAlchemy engine, declarative ``Base`` and the per-request session dependency.

Transactions are explicit: ``get_db()`` never commits. A service that wants its writes
kept calls ``await session.commit()``; anything else is rolled back when the session
closes. This keeps "business write + task enqueue" boundaries visible in the service.
"""

import logging
from collections.abc import AsyncIterator

import google.auth
import google.auth.credentials
from sqlalchemy import MetaData, event, func, select
from sqlalchemy.engine import URL, Engine, make_url
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


_IAM_LOGIN_SCOPE = "https://www.googleapis.com/auth/sqlservice.login"
_credentials: google.auth.credentials.Credentials | None = None


def iam_password() -> str:
    """Access token of the runtime service account, used as the Postgres password (ADR 0028).
    Valid ~1 h and checked only at connect time, so the pool needs nothing but a fresh value
    per new connection. Blocking HTTP (rare: one refresh per hour per process)."""
    global _credentials
    from google.auth.transport.requests import Request  # lazy: only IAM logins need it

    if _credentials is None:
        _credentials, _ = google.auth.default(scopes=[_IAM_LOGIN_SCOPE])
    if not _credentials.valid:
        _credentials.refresh(Request())  # type: ignore[no-untyped-call]
    return str(_credentials.token)


def database_url(settings: Settings) -> URL:
    """The validated ``postgresql+psycopg`` URL; with IAM auth the user is ``db_iam_user`` and
    any password in the secret is dropped (the token is injected per connection)."""
    url = make_url(settings.database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError(
            "DATABASE_URL must use the psycopg driver (postgresql+psycopg://)"
        )
    if settings.db_iam_auth:
        # URL.set(password=None) means "unchanged"; _replace really clears it.
        url = url.set(username=settings.db_iam_user or url.username)._replace(
            password=None
        )
    return url


def use_iam_password(engine: Engine) -> None:
    """Make every new connection of this (sync) engine log in with a fresh IAM token."""

    @event.listens_for(engine, "do_connect")
    def _inject(_dialect: object, _rec: object, _cargs: object, cparams: dict) -> None:  # type: ignore[type-arg]
        cparams["password"] = iam_password()


def create_engine(
    settings: Settings, *, application_name: str = "recruitai-api"
) -> AsyncEngine:
    """Build the engine on the psycopg (v3) async driver (ADR 0017)."""
    url = database_url(settings)
    options = (
        f"-c statement_timeout={settings.db_statement_timeout_ms} "
        f"-c idle_in_transaction_session_timeout={settings.db_idle_in_transaction_timeout_ms}"
    )
    engine = create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
        pool_recycle=settings.db_pool_recycle_s,
        pool_pre_ping=True,
        connect_args={"options": options, "application_name": application_name},
    )
    if settings.db_iam_auth:
        use_iam_password(engine.sync_engine)
    return engine


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


async def warm_up() -> None:
    """Open (and return to the pool) one connection so the first real request does not pay for
    it. Never raises: a failure here just means the request connects itself."""
    if _session_factory is None:
        return
    try:
        async with _session_factory() as session:
            await session.execute(select(1))
    except Exception:  # noqa: BLE001 - best effort, the request path reports real errors
        logging.getLogger(__name__).warning("db_warm_up_failed")


async def get_db() -> AsyncIterator[AsyncSession]:
    """Session-per-request dependency. Does not commit; see the module docstring."""
    if _session_factory is None:
        raise RuntimeError("database not initialised (init_db was not called)")
    async with _session_factory() as session:
        yield session


async def count_rows(session: AsyncSession, model: type[Base]) -> int:
    """Row count of a whole table, for platform statistics (admin only, never per tenant)."""
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()
