"""Alembic environment. Sync psycopg engine: migrations don't need async, and a sync run
can be called from any plain test or CLI without an event loop."""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

import recruitai.models  # noqa: F401  (registers every table on Base.metadata)
from alembic import context
from recruitai.config import Settings
from recruitai.core.db import Base, database_url, use_iam_password

config = context.config
if config.config_file_name and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _settings_iam() -> bool:
    return not config.get_main_option("sqlalchemy.url") and Settings().db_iam_auth  # type: ignore[call-arg]


def _database_url() -> str:
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        parsed = make_url(explicit)
        if parsed.drivername == "postgresql":
            parsed = parsed.set(drivername="postgresql+psycopg")
        return parsed.render_as_string(hide_password=False)
    return database_url(Settings()).render_as_string(hide_password=False)  # type: ignore[call-arg]


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    if _settings_iam():
        use_iam_password(engine)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
