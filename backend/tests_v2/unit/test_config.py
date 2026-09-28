import pytest
from pydantic import ValidationError

from recruitai.config import Settings


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
