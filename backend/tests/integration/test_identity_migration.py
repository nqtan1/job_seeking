"""P1-02: the identity migration. Structure + round trip on a scratch database."""

import re

from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from alembic import command
from tests.fixtures.migrations import alembic_config

TABLES = {"organizations", "users", "memberships"}


def _allowed(sqltext: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", sqltext))


def _tables(url: URL) -> set[str]:
    engine = create_engine(url.set(drivername="postgresql+psycopg"), poolclass=NullPool)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_identity_tables_columns_constraints_and_indexes(scratch_migration_db):
    command.upgrade(alembic_config(scratch_migration_db), "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    insp = inspect(engine)
    try:
        assert TABLES <= set(insp.get_table_names())

        def cols(table):
            return {c["name"]: c for c in insp.get_columns(table)}

        org, user, mem = cols("organizations"), cols("users"), cols("memberships")
        for c in (org, user, mem):
            assert str(c["id"]["type"]) == "UUID"
            assert (
                c["created_at"]["type"].timezone is True
                and c["created_at"]["nullable"] is False
            )
            assert c["created_at"]["default"] is not None  # server default now()
        required = lambda c: {n for n, v in c.items() if not v["nullable"]}
        assert required(org) == {"id", "name", "kind", "created_at"}
        assert required(user) == {"id", "firebase_uid", "email", "created_at"}
        assert required(mem) == {"id", "org_id", "user_id", "role", "created_at"}
        assert (
            user["last_active_at"]["type"].timezone
            and user["deletion_warned_at"]["type"].timezone
        )

        assert {
            u["name"]: u["column_names"] for u in insp.get_unique_constraints("users")
        } == {"uq_users_firebase_uid": ["firebase_uid"]}
        assert {
            u["name"]: u["column_names"]
            for u in insp.get_unique_constraints("memberships")
        } == {"uq_memberships_org_id_user_id": ["org_id", "user_id"]}
        fks = {f["name"]: f for f in insp.get_foreign_keys("memberships")}
        for name, table in (
            ("fk_memberships_org_id_organizations", "organizations"),
            ("fk_memberships_user_id_users", "users"),
        ):
            assert (
                fks[name]["referred_table"] == table
                and fks[name]["options"]["ondelete"] == "CASCADE"
            )
        indexes = {
            i["name"]: i["column_names"] for i in insp.get_indexes("memberships")
        }
        assert indexes["ix_memberships_org_id_created_at"] == [
            "org_id",
            "created_at",
        ]  # tenant-table rule
        assert indexes["ix_memberships_user_id"] == ["user_id"]

        checks = {
            c["name"]: c["sqltext"]
            for t in ("organizations", "memberships")
            for c in insp.get_check_constraints(t)
        }
        assert set(checks) == {"ck_organizations_kind", "ck_memberships_role"}
        assert _allowed(checks["ck_organizations_kind"]) == {"personal", "company"}
        assert _allowed(checks["ck_memberships_role"]) == {
            "owner",
            "recruiter",
            "member",
        }
        for t in TABLES:
            assert insp.get_pk_constraint(t)["name"] == f"pk_{t}"
    finally:
        engine.dispose()


def test_migrations_round_trip_have_one_head_and_no_model_drift(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # a second upgrade is a no-op
    command.check(cfg)  # raises if models and migrations have drifted

    command.downgrade(cfg, "base")
    assert _tables(scratch_migration_db) <= {"alembic_version"}  # nothing left behind

    command.upgrade(cfg, "0001")  # every revision is reachable and reversible
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert TABLES <= _tables(scratch_migration_db)
