"""P1-03: structure of the `documents` and `ai_calls` tables (scratch DB, real migrations)."""

import re
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from alembic import command
from tests.fixtures.migrations import alembic_config

AI_CALLS_COLUMNS = {
    "id", "org_id", "user_id", "feature", "model", "prompt_version",
    "input_tokens", "output_tokens", "latency_ms", "status", "created_at",
}  # fmt: skip


@pytest.fixture
def insp(scratch_migration_db: URL):
    command.upgrade(alembic_config(scratch_migration_db), "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    yield inspect(engine)
    engine.dispose()


def _cols(insp, table):
    return {c["name"]: c for c in insp.get_columns(table)}


def _allowed(sqltext: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", sqltext))


def test_registry_alone_registers_every_table_in_a_fresh_interpreter():
    """`alembic` and `alembic check` only import `recruitai.models`. Other test modules import
    models directly, so this must run in a clean process to prove the registry is complete."""
    code = (
        "import recruitai.models; from recruitai.core.db import Base; "
        "print(','.join(sorted(Base.metadata.tables)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()

    assert set(out.split(",")) == {
        "ai_calls",
        "documents",
        "memberships",
        "organizations",
        "users",
    }


def test_documents_columns(insp):
    cols = _cols(insp, "documents")

    assert set(cols) == {
        "id", "org_id", "kind", "storage_key", "mime", "size", "sha256", "uploaded_by", "created_at",
    }  # fmt: skip
    assert {c for c, v in cols.items() if not v["nullable"]} == set(cols) - {
        "uploaded_by"
    }
    assert str(cols["size"]["type"]) == "BIGINT"  # files can exceed 2 GiB in principle
    assert cols["created_at"]["type"].timezone is True


def test_documents_constraints_and_indexes(insp):
    checks = {c["name"]: c["sqltext"] for c in insp.get_check_constraints("documents")}
    assert set(checks) == {
        "ck_documents_kind",
        "ck_documents_size",
        "ck_documents_sha256",
    }
    assert _allowed(checks["ck_documents_kind"]) == {
        "cv",
        "jd",
        "letter_pdf",
        "attachment",
    }

    assert {
        u["name"]: u["column_names"] for u in insp.get_unique_constraints("documents")
    } == {"uq_documents_storage_key": ["storage_key"]}
    fks = {f["name"]: f for f in insp.get_foreign_keys("documents")}
    assert fks["fk_documents_org_id_organizations"]["options"]["ondelete"] == "CASCADE"
    assert fks["fk_documents_uploaded_by_users"]["options"]["ondelete"] == "SET NULL"
    indexes = {i["name"]: i["column_names"] for i in insp.get_indexes("documents")}
    assert indexes["ix_documents_org_id_created_at"] == ["org_id", "created_at"]


def test_ai_calls_columns_are_metadata_only(insp):
    """Privacy guard (ADR 0014): a prompt/response/content column must never appear here.
    If you genuinely need a new metadata column, extend AI_CALLS_COLUMNS deliberately."""
    cols = _cols(insp, "ai_calls")

    assert set(cols) == AI_CALLS_COLUMNS
    assert {c for c, v in cols.items() if not v["nullable"]} == AI_CALLS_COLUMNS - {
        "user_id"
    }
    assert cols["created_at"]["type"].timezone is True


def test_ai_calls_constraints_and_indexes(insp):
    checks = {c["name"]: c["sqltext"] for c in insp.get_check_constraints("ai_calls")}
    assert set(checks) == {
        "ck_ai_calls_status",
        "ck_ai_calls_tokens",
        "ck_ai_calls_latency",
    }
    assert _allowed(checks["ck_ai_calls_status"]) == {"ok", "error"}

    fks = {f["name"]: f for f in insp.get_foreign_keys("ai_calls")}
    assert fks["fk_ai_calls_org_id_organizations"]["options"]["ondelete"] == "CASCADE"
    assert fks["fk_ai_calls_user_id_users"]["options"]["ondelete"] == "SET NULL"
    indexes = {i["name"]: i["column_names"] for i in insp.get_indexes("ai_calls")}
    assert indexes["ix_ai_calls_org_id_created_at"] == ["org_id", "created_at"]


def test_one_step_down_from_head_keeps_identity_and_drops_the_new_tables(
    scratch_migration_db,
):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "-1")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {"organizations", "users", "memberships"} <= tables
    assert not ({"documents", "ai_calls"} & tables)

    command.upgrade(cfg, "head")  # and back up
