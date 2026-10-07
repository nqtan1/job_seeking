import re
import subprocess
import sys
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
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
        assert required(user) == {
            "id",
            "firebase_uid",
            "email",
            "created_at",
            "email_reminders",
        }
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


AI_CALLS_COLUMNS = {
    "id",
    "org_id",
    "user_id",
    "feature",
    "model",
    "prompt_version",
    "input_tokens",
    "output_tokens",
    "latency_ms",
    "status",
    "created_at",
}


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
        "admin_actions",
        "ai_setting_changes",
        "ai_settings",
        "ai_calls",
        "application_documents",
        "application_events",
        "applications",
        "candidate_profiles",
        "conversations",
        "documents",
        "fit_analyses",
        "job_postings",
        "job_search_cache",
        "letter_versions",
        "letters",
        "memberships",
        "messages",
        "organizations",
        "radar_results",
        "radar_runs",
        "radar_searches",
        "task_runs",
        "users",
    }


def test_documents_columns_constraints_and_indexes(insp):
    cols = _cols(insp, "documents")

    assert set(cols) == {
        "id", "org_id", "kind", "storage_key", "mime", "size", "sha256", "uploaded_by", "created_at",
    }  # fmt: skip
    assert {c for c, v in cols.items() if not v["nullable"]} == set(cols) - {
        "uploaded_by"
    }
    assert str(cols["size"]["type"]) == "BIGINT"  # files can exceed 2 GiB in principle
    assert cols["created_at"]["type"].timezone is True
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
        "export",
    }

    assert {
        u["name"]: u["column_names"] for u in insp.get_unique_constraints("documents")
    } == {"uq_documents_storage_key": ["storage_key"]}
    fks = {f["name"]: f for f in insp.get_foreign_keys("documents")}
    assert fks["fk_documents_org_id_organizations"]["options"]["ondelete"] == "CASCADE"
    assert fks["fk_documents_uploaded_by_users"]["options"]["ondelete"] == "SET NULL"
    indexes = {i["name"]: i["column_names"] for i in insp.get_indexes("documents")}
    assert indexes["ix_documents_org_id_created_at"] == ["org_id", "created_at"]


def test_ai_calls_are_metadata_only_with_the_expected_constraints(insp):
    """Privacy guard (ADR 0014): a prompt/response/content column must never appear here.
    If you genuinely need a new metadata column, extend AI_CALLS_COLUMNS deliberately."""
    cols = _cols(insp, "ai_calls")

    assert set(cols) == AI_CALLS_COLUMNS
    assert {c for c, v in cols.items() if not v["nullable"]} == AI_CALLS_COLUMNS - {
        "user_id"
    }
    assert cols["created_at"]["type"].timezone is True
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


def test_downgrade_to_0001_keeps_identity_and_drops_documents_and_ai_calls(
    scratch_migration_db,
):
    """Named revision, not "-1" (one step down from *whatever head currently is*): this
    test is specifically about revision 0002's downgrade, and must keep testing exactly
    that regardless of how many later migrations (0003+) get added on top."""
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "0001")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {"organizations", "users", "memberships"} <= tables
    assert not ({"documents", "ai_calls"} & tables)

    command.upgrade(cfg, "head")


def test_candidate_profiles_structure_and_downgrade(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        insp = inspect(engine)
        cols = {c["name"]: c for c in insp.get_columns("candidate_profiles")}
        assert set(cols) == {
            "id", "org_id", "document_id", "name", "email", "data",
            "schema_version", "created_at", "updated_at",
        }  # fmt: skip
        assert not cols["data"]["nullable"] and not cols["org_id"]["nullable"]
        assert cols["document_id"]["nullable"]
        assert [
            u["column_names"] for u in insp.get_unique_constraints("candidate_profiles")
        ] == [["org_id"]]
        ondelete = {
            fk["referred_table"]: fk["options"]["ondelete"]
            for fk in insp.get_foreign_keys("candidate_profiles")
        }
        assert ondelete == {"organizations": "CASCADE", "documents": "SET NULL"}
    finally:
        engine.dispose()

    command.downgrade(cfg, "0003")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        assert "candidate_profiles" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_fit_analyses_structure_constraints_and_downgrade(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        insp = inspect(engine)
        assert {c["name"] for c in insp.get_columns("fit_analyses")} == {
            "id", "org_id", "candidate_id", "job_id", "company_type", "score",
            "verdict", "data", "schema_version", "model", "prompt_version", "created_at",
        }  # fmt: skip
        ondelete = {
            fk["referred_table"]: fk["options"]["ondelete"]
            for fk in insp.get_foreign_keys("fit_analyses")
        }
        assert ondelete == {
            "organizations": "CASCADE",
            "candidate_profiles": "CASCADE",
            "job_postings": "CASCADE",
        }
        assert {i["name"] for i in insp.get_indexes("fit_analyses")} == {
            "ix_fit_analyses_org_id_created_at",
            "ix_fit_analyses_org_id_job_id",
        }

        org, cand, job = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, kind) VALUES (:i, 'o', 'personal')"
                ),
                {"i": org},
            )
            conn.execute(
                text(
                    "INSERT INTO candidate_profiles (id, org_id, name, data, schema_version)"
                    " VALUES (:i, :o, 'n', '{}', 1)"
                ),
                {"i": cand, "o": org},
            )
            conn.execute(
                text(
                    "INSERT INTO job_postings (id, org_id, source, title, data, schema_version)"
                    " VALUES (:i, :o, 'manual', 't', '{}', 1)"
                ),
                {"i": job, "o": org},
            )

        def add(score: int, verdict: str, company_type: str) -> None:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO fit_analyses (id, org_id, candidate_id, job_id,"
                        " company_type, score, verdict, data, schema_version, model,"
                        " prompt_version) VALUES (:id, :o, :c, :j, :ct, :s, :v, '{}', 1,"
                        " 'm', 'fit@1')"
                    ),
                    {"id": uuid.uuid4(), "o": org, "c": cand, "j": job,
                     "ct": company_type, "s": score, "v": verdict},
                )  # fmt: skip

        add(80, "go", "startup")
        add(
            80, "go", "startup"
        )  # re-running an analysis is allowed: history, not upsert
        for bad in ((101, "go", "phd"), (50, "hire", "phd"), (50, "go", "ngo")):
            with pytest.raises(IntegrityError):
                add(*bad)
    finally:
        engine.dispose()

    command.downgrade(cfg, "0005")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        assert "fit_analyses" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_jobs_tables_constraints_and_downgrade(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("job_postings")}
        assert cols == {
            "id", "org_id", "source", "external_id", "title", "company", "data",
            "schema_version", "created_at",
        }  # fmt: skip
        assert {c["name"] for c in insp.get_columns("job_search_cache")} == {
            "key", "provider", "payload", "expires_at",
        }  # fmt: skip
        assert [
            u["column_names"] for u in insp.get_unique_constraints("job_postings")
        ] == [["org_id", "source", "external_id"]]

        org = uuid.uuid4()
        insert = text(
            "INSERT INTO job_postings (id, org_id, source, external_id, title, data,"
            " schema_version) VALUES (:id, :org, :src, :ext, 't', '{}', 1)"
        )

        def add(conn, src: str, ext: str | None) -> None:
            conn.execute(
                insert, {"id": uuid.uuid4(), "org": org, "src": src, "ext": ext}
            )

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, kind) VALUES (:i, 'o', 'personal')"
                ),
                {"i": org},
            )
            add(conn, "france_travail", "212MZBL")
            add(conn, "manual", None)
            add(conn, "manual", None)  # NULL external ids never collide
        with pytest.raises(IntegrityError), engine.begin() as conn:
            add(conn, "france_travail", "212MZBL")  # same (org, source, external_id)
        with pytest.raises(IntegrityError), engine.begin() as conn:
            add(conn, "url", None)  # D5: no URL source
    finally:
        engine.dispose()

    command.downgrade(cfg, "0004")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        tables = inspect(engine).get_table_names()
        assert "job_postings" not in tables and "job_search_cache" not in tables
    finally:
        engine.dispose()


def test_coach_tables_constraints_and_downgrade(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        insp = inspect(engine)
        assert {c["name"] for c in insp.get_columns("conversations")} == {
            "id", "org_id", "candidate_id", "job_id", "started_at",
        }  # fmt: skip
        assert {c["name"] for c in insp.get_columns("messages")} == {
            "id", "conversation_id", "org_id", "role", "content", "created_at",
        }  # fmt: skip
        conv_fk = {
            fk["referred_table"]: fk["options"]["ondelete"]
            for fk in insp.get_foreign_keys("conversations")
        }
        assert conv_fk == {
            "organizations": "CASCADE",
            "candidate_profiles": "CASCADE",
            "job_postings": "SET NULL",
        }
        assert {i["name"] for i in insp.get_indexes("messages")} == {
            "ix_messages_conversation_id_created_at",
            "ix_messages_org_id_created_at",
        }

        org, cand, conv = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, kind) VALUES (:i, 'o', 'personal')"
                ),
                {"i": org},
            )
            conn.execute(
                text(
                    "INSERT INTO candidate_profiles (id, org_id, name, data, schema_version)"
                    " VALUES (:i, :o, 'n', '{}', 1)"
                ),
                {"i": cand, "o": org},
            )
            conn.execute(
                text(
                    "INSERT INTO conversations (id, org_id, candidate_id) VALUES (:i, :o, :c)"
                ),
                {"i": conv, "o": org, "c": cand},
            )

        def add_message(role: str) -> None:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO messages (id, conversation_id, org_id, role, content)"
                        " VALUES (:i, :c, :o, :r, 'hello')"
                    ),
                    {"i": uuid.uuid4(), "c": conv, "o": org, "r": role},
                )

        add_message("user")
        add_message("assistant")
        with pytest.raises(IntegrityError):
            add_message("system")  # only user and assistant turns are stored
        with engine.begin() as conn:  # messages die with their conversation
            conn.execute(text("DELETE FROM conversations WHERE id = :i"), {"i": conv})
            assert conn.execute(text("SELECT count(*) FROM messages")).scalar() == 0
    finally:
        engine.dispose()

    command.downgrade(cfg, "0007")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        tables = inspect(engine).get_table_names()
        assert "conversations" not in tables and "messages" not in tables
    finally:
        engine.dispose()


def test_applications_tables_constraints_and_downgrade(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        insp = inspect(engine)
        cols = {c["name"]: c for c in insp.get_columns("applications")}
        assert set(cols) == {
            "id", "org_id", "job_id", "company_name", "job_title", "source", "status",
            "applied_at", "notes", "interview_at", "contact", "created_at", "updated_at",
        }  # fmt: skip
        assert cols["job_id"]["nullable"]  # a manual application has no linked job
        ondelete = {
            fk["referred_table"]: fk["options"]["ondelete"]
            for fk in insp.get_foreign_keys("applications")
        }
        assert ondelete == {"organizations": "CASCADE", "job_postings": "SET NULL"}

        org, app = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, kind) VALUES (:i, 'o', 'personal')"
                ),
                {"i": org},
            )

        def add_application(**over: str) -> None:
            row = {"id": app, "o": org, "src": "linkedin", "st": None, **over}
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO applications (id, org_id, company_name, source)"
                        " VALUES (:id, :o, 'Acme', :src)"
                    )
                    if row["st"] is None
                    else text(
                        "INSERT INTO applications (id, org_id, company_name, source, status)"
                        " VALUES (:id, :o, 'Acme', :src, :st)"
                    ),
                    row,
                )

        add_application()
        with engine.connect() as conn:
            default = conn.execute(
                text("SELECT status FROM applications WHERE id=:i"), {"i": app}
            )
            assert default.scalar() == "to_apply"
        for bad in ({"src": "tiktok"}, {"st": "hired", "id": uuid.uuid4()}):
            with pytest.raises(IntegrityError):
                add_application(**bad)

        def add_event(frm: str | None, to: str) -> None:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO application_events (id, application_id, org_id,"
                        " from_status, to_status, at) VALUES (:i, :a, :o, :f, :t, now())"
                    ),
                    {"i": uuid.uuid4(), "a": app, "o": org, "f": frm, "t": to},
                )

        add_event(None, "to_apply")  # the creation event has no "from"
        add_event("to_apply", "applied")
        for bad_event in (("applied", "hired"), ("nope", "applied")):
            with pytest.raises(IntegrityError):
                add_event(*bad_event)
        with engine.begin() as conn:  # events die with their application
            conn.execute(text("DELETE FROM applications WHERE id=:i"), {"i": app})
            assert (
                conn.execute(text("SELECT count(*) FROM application_events")).scalar()
                == 0
            )
    finally:
        engine.dispose()

    command.downgrade(cfg, "0008")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        tables = inspect(engine).get_table_names()
        assert "applications" not in tables and "application_events" not in tables
    finally:
        engine.dispose()


def test_letters_structure_constraints_and_downgrade(scratch_migration_db):
    cfg = alembic_config(scratch_migration_db)
    command.upgrade(cfg, "head")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("letters")}
        assert cols == {
            "id", "org_id", "job_id", "kind", "template", "content", "latex_override",
            "language", "tone", "length", "company_type", "status", "render_status",
            "pdf_document_id", "schema_version", "created_at", "updated_at",
        }  # fmt: skip
        assert (
            not {"expires_at", "expiry"} & cols
        )  # drafts are ordinary rows (§4.7/§11.2)
        ondelete = {
            fk["referred_table"]: fk["options"]["ondelete"]
            for fk in insp.get_foreign_keys("letters")
        }
        assert ondelete == {
            "organizations": "CASCADE",
            "job_postings": "SET NULL",
            "documents": "SET NULL",
        }
        assert insp.get_pk_constraint("letter_versions")["constrained_columns"] == [
            "letter_id", "n",
        ]  # fmt: skip

        org, letter = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO organizations (id, name, kind) VALUES (:i, 'o', 'personal')"
                ),
                {"i": org},
            )

        def add_letter(**over: str) -> uuid.UUID:
            row = {"id": uuid.uuid4(), "o": org, "lang": "fr", "tone": "warm",
                   "len": "short", "ct": "startup", **over}  # fmt: skip
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO letters (id, org_id, content, language, tone, length,"
                        " company_type, schema_version) VALUES (:id, :o, '{}', :lang, :tone,"
                        " :len, :ct, 1)"
                    ),
                    row,
                )
            return row["id"]  # type: ignore[return-value]

        letter = add_letter()
        with engine.connect() as conn:
            defaults = conn.execute(
                text(
                    "SELECT kind, template, status, render_status FROM letters WHERE id=:i"
                ),
                {"i": letter},
            ).one()
        assert tuple(defaults) == ("cover", "classic", "draft", "none")

        for bad in ({"lang": "de"}, {"tone": "rude"}, {"len": "epic"}, {"ct": "ngo"}):
            with pytest.raises(IntegrityError):
                add_letter(**bad)

        def add_version(n: int) -> None:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO letter_versions (letter_id, n, org_id, content)"
                        " VALUES (:l, :n, :o, '{}')"
                    ),
                    {"l": letter, "n": n, "o": org},
                )

        add_version(1)
        add_version(2)
        with pytest.raises(IntegrityError):
            add_version(2)  # (letter_id, n) is unique
        with engine.begin() as conn:  # versions die with their letter
            conn.execute(text("DELETE FROM letters WHERE id=:i"), {"i": letter})
            left = conn.execute(text("SELECT count(*) FROM letter_versions")).scalar()
        assert left == 0
    finally:
        engine.dispose()

    command.downgrade(cfg, "0006")
    engine = create_engine(
        scratch_migration_db.set(drivername="postgresql+psycopg"), poolclass=NullPool
    )
    try:
        tables = inspect(engine).get_table_names()
        assert "letters" not in tables and "letter_versions" not in tables
    finally:
        engine.dispose()
