"""P1-02: the identity migration. Structure + round trip on a scratch database."""

import re

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from alembic import command
from tests.fixtures.migrations import alembic_config

TABLES = {"organizations", "users", "memberships"}


def _inspector(url: URL):
    engine = create_engine(url.set(drivername="postgresql+psycopg"), poolclass=NullPool)
    return engine, inspect(engine)


def _allowed(sqltext: str) -> set[str]:
    return set(re.findall(r"'([^']+)'", sqltext))


def _tables(url: URL) -> set[str]:
    engine, insp = _inspector(url)
    try:
        return set(insp.get_table_names())
    finally:
        engine.dispose()


def test_there_is_exactly_one_migration_head(scratch_migration_db):
    script = ScriptDirectory.from_config(alembic_config(scratch_migration_db))

    assert len(script.get_heads()) == 1


def test_upgrade_head_creates_the_identity_tables(scratch_migration_db):
    command.upgrade(alembic_config(scratch_migration_db), "head")

    assert TABLES <= _tables(scratch_migration_db)


def test_identity_columns_types_and_nullability(scratch_migration_db):
    command.upgrade(alembic_config(scratch_migration_db), "head")
    engine, insp = _inspector(scratch_migration_db)
    try:

        def cols(table):
            return {c["name"]: c for c in insp.get_columns(table)}

        org, user, mem = cols("organizations"), cols("users"), cols("memberships")
        for table_cols in (org, user, mem):
            assert str(table_cols["id"]["type"]) == "UUID"
            assert table_cols["created_at"]["type"].timezone is True
            assert table_cols["created_at"]["nullable"] is False
            assert (
                table_cols["created_at"]["default"] is not None
            )  # server default now()
        assert {c for c, v in org.items() if not v["nullable"]} == {
            "id",
            "name",
            "kind",
            "created_at",
        }
        assert {c for c, v in user.items() if not v["nullable"]} == {
            "id",
            "firebase_uid",
            "email",
            "created_at",
        }
        assert {"display_name", "last_active_at", "deletion_warned_at"} <= set(user)
        assert user["last_active_at"]["type"].timezone is True
        assert user["deletion_warned_at"]["type"].timezone is True
        assert {c for c, v in mem.items() if not v["nullable"]} == {
            "id",
            "org_id",
            "user_id",
            "role",
            "created_at",
        }
    finally:
        engine.dispose()


def test_identity_constraints_and_indexes(scratch_migration_db):
    command.upgrade(alembic_config(scratch_migration_db), "head")
    engine, insp = _inspector(scratch_migration_db)
    try:
        uniques = {
            t: {u["name"]: u["column_names"] for u in insp.get_unique_constraints(t)}
            for t in TABLES
        }
        assert uniques["users"] == {"uq_users_firebase_uid": ["firebase_uid"]}
        assert uniques["memberships"] == {
            "uq_memberships_org_id_user_id": ["org_id", "user_id"]
        }

        fks = {f["name"]: f for f in insp.get_foreign_keys("memberships")}
        assert (
            fks["fk_memberships_org_id_organizations"]["referred_table"]
            == "organizations"
        )
        assert (
            fks["fk_memberships_org_id_organizations"]["options"]["ondelete"]
            == "CASCADE"
        )
        assert fks["fk_memberships_user_id_users"]["referred_table"] == "users"
        assert fks["fk_memberships_user_id_users"]["options"]["ondelete"] == "CASCADE"

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


def test_downgrade_base_removes_everything_and_upgrade_works_again(
    scratch_migration_db,
):
    cfg = alembic_config(scratch_migration_db)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert _tables(scratch_migration_db) <= {"alembic_version"}

    command.upgrade(cfg, "head")  # up / down / up
    assert TABLES <= _tables(scratch_migration_db)


def test_upgrade_head_twice_is_a_noop(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")

    command.upgrade(cfg, "head")

    assert TABLES <= _tables(scratch_migration_db)


def test_models_and_migrations_have_not_drifted(scratch_migration_db):
    """`alembic check`: fails if a model changed without a migration (or vice versa)."""
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")

    command.check(cfg)  # raises CommandError when autogenerate would produce changes


@pytest.mark.parametrize("target", ["0001"])
def test_each_revision_can_be_reached_and_left(scratch_migration_db, target):
    cfg = alembic_config(scratch_migration_db)

    command.upgrade(cfg, target)
    command.downgrade(cfg, "base")

    assert _tables(scratch_migration_db) <= {"alembic_version"}
