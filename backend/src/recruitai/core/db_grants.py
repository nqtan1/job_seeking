"""Run by the migrate job after Alembic and the Procrastinate schema (ADR 0028):
``python -m recruitai.core.db_grants``. The migrator identity owns the schema; the API and
worker identities (``DB_APP_ROLES``, comma-separated IAM DB users) get data access only, never
DDL. Idempotent, so it re-applies on every deploy and covers tables a migration just added."""

import os

import psycopg
from psycopg import sql

from recruitai.config import Settings
from recruitai.core.db import database_url, iam_password

_GRANTS = (
    "GRANT USAGE ON SCHEMA public TO {r}",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {r}",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {r}",
    "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {r}",
)


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    roles = [r.strip() for r in os.environ["DB_APP_ROLES"].split(",") if r.strip()]
    url = database_url(settings).set(drivername="postgresql")
    password = iam_password() if settings.db_iam_auth else url.password
    with psycopg.connect(
        url.render_as_string(hide_password=False), password=password, autocommit=True
    ) as conn:
        for role in roles:
            for stmt in _GRANTS:
                conn.execute(sql.SQL(stmt).format(r=sql.Identifier(role)))
    print(f"grants applied to {len(roles)} role(s)")


if __name__ == "__main__":
    main()
