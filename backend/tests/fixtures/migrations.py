"""Alembic helpers for tests. Migrations run through the real Alembic API against
TEST_DATABASE_URL; the round-trip tests use their own throwaway database."""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import URL

from alembic import command

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DB = "recruitai_test_migrations"


def alembic_config(url: URL) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%")
    )
    cfg.attributes["skip_logging"] = True
    return cfg


@pytest.fixture(scope="session")
def migrated_test_db(test_database_url: URL) -> URL:
    """The shared test database, rebuilt from scratch with ``alembic upgrade head`` every
    session, so tests can never pass against a stale schema left over from an older migration."""
    with psycopg.connect(
        test_database_url.set(drivername="postgresql").render_as_string(
            hide_password=False
        ),
        autocommit=True,
    ) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    command.upgrade(alembic_config(test_database_url), "head")
    return test_database_url


@pytest.fixture
def scratch_migration_db(test_database_url: URL) -> Iterator[URL]:
    """An empty database that only one test uses, for up/down round trips."""
    admin = test_database_url.set(drivername="postgresql", database="postgres")
    scratch = test_database_url.set(database=MIGRATIONS_DB)
    with psycopg.connect(
        admin.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(MIGRATIONS_DB)
            )
        )
        conn.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(MIGRATIONS_DB))
        )
    yield scratch
    with psycopg.connect(
        admin.render_as_string(hide_password=False), autocommit=True
    ) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(MIGRATIONS_DB)
            )
        )
