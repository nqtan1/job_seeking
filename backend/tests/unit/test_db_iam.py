"""Cloud SQL IAM auth (ADR 0028): the URL loses its password and every new connection gets a
fresh token. No network: the token source is monkeypatched."""

from sqlalchemy import create_engine

from recruitai.config import Settings
from recruitai.core import db


def test_iam_url_and_token_injection(monkeypatch) -> None:
    monkeypatch.setattr(db, "iam_password", lambda: "tok-1")
    base = {"env": "local", "firebase_project_id": "p"}
    url = "postgresql://old:secret@10.0.0.5/recruitai"

    plain = db.database_url(Settings(**base, database_url=url))
    assert (plain.username, plain.password) == ("old", "secret")

    iam = db.database_url(
        Settings(**base, database_url=url, db_iam_auth=True, db_iam_user="svc@p.iam")
    )
    assert (iam.username, iam.password) == ("svc@p.iam", None)

    engine = create_engine("postgresql+psycopg://svc@localhost/x")
    db.use_iam_password(engine)
    cparams: dict[str, str] = {}
    engine.dialect.dispatch.do_connect(engine.dialect, None, (), cparams)
    assert cparams["password"] == "tok-1"
