"""Real ``LocalStorage`` pointed at a temp directory — not a hand-rolled fake, so tests
exercise the exact same code path production dev/test traffic uses (P1-09)."""

from pathlib import Path

import pytest

from recruitai.core.storage import LocalStorage

TEST_SIGNING_SECRET = "test-signing-secret"


@pytest.fixture
def fake_storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(root=tmp_path, signing_secret=TEST_SIGNING_SECRET)
