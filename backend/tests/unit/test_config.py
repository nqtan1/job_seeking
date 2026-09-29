import pytest
from pydantic import ValidationError

from recruitai.config import Settings

DB = "postgresql+psycopg://u:p@localhost:5432/x_test"


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_missing_database_url_raises(monkeypatch):
    monkeypatch.setenv("ENV", "local")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_with_emulator_host_raises(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", DB)
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_without_emulator_host_is_fine(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", DB)
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)

    Settings(_env_file=None)
