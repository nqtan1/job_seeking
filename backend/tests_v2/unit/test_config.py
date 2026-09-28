import pytest
from pydantic import ValidationError

from recruitai.config import Settings


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_with_emulator_host_raises(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_prod_without_emulator_host_is_fine(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)

    Settings(_env_file=None)
