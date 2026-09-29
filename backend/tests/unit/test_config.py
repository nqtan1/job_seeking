import pytest
from pydantic import ValidationError

from recruitai.config import Settings

DB = "postgresql+psycopg://u:p@localhost:5432/x_test"


def test_missing_required_settings_fail_fast(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("DATABASE_URL", DB)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("ENV", "local")
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_refuses_the_firebase_emulator(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", DB)
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST")
    Settings(_env_file=None)  # fine without the emulator
