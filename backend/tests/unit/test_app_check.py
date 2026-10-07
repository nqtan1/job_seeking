"""core/app_check.py (P1-17): App Check verification dependency.

"Valid token passes" is mocked, not tested against a real token: firebase-admin's
app_check.verify_token() always checks a real RS256 signature against Google's live JWKS
endpoint (confirmed by reading the installed library — no emulator shortcut exists the way
core/auth.py's ID-token verification has). Producing a genuinely valid token would need a
real Firebase project and a real attestation provider (reCAPTCHA, Play Integrity); mocking
verify_token proves our dependency's control flow is correct either way.
"""

from unittest.mock import patch

import pytest
from firebase_admin import app_check

from recruitai.config import Settings
from recruitai.core.app_check import verify_app_check
from recruitai.core.auth import get_firebase_app
from recruitai.core.errors import Unauthorized


def _settings(**overrides) -> Settings:
    base = {
        "env": "local",
        "database_url": "postgresql+psycopg://u:p@localhost/x_test",
        "firebase_project_id": "demo-recruitai",  # same as conftest: this initializes the process-wide Firebase app
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


async def test_valid_token_passes():
    settings = _settings()
    with patch.object(app_check, "verify_token", return_value={"app_id": "1:2:web:3"}):
        await verify_app_check(
            settings,
            get_firebase_app(settings),
            x_firebase_appcheck="a-valid-looking-token",
        )  # no exception


async def test_missing_token_is_401():
    settings = _settings()
    with pytest.raises(Unauthorized, match="Missing"):
        await verify_app_check(
            settings, get_firebase_app(settings), x_firebase_appcheck=None
        )


async def test_invalid_token_is_401():
    settings = _settings()
    with (
        patch.object(
            app_check, "verify_token", side_effect=ValueError("bad signature")
        ),
        pytest.raises(Unauthorized, match="Invalid or expired"),
    ):
        await verify_app_check(
            settings, get_firebase_app(settings), x_firebase_appcheck="garbage"
        )


async def test_disabled_in_local_skips_verification_entirely():
    """No header at all, and verify_token is never even called."""
    settings = _settings(app_check_enforced=False)
    with patch.object(app_check, "verify_token") as mocked:
        await verify_app_check(
            settings, get_firebase_app(settings), x_firebase_appcheck=None
        )
    mocked.assert_not_called()


async def test_disabling_only_applies_to_local():
    """app_check_enforced=False on a non-local env (dev/staging) still enforces — only
    ENV=local gets the escape hatch, matching the task's literal wording."""
    settings = _settings(env="dev", app_check_enforced=False)
    with pytest.raises(Unauthorized, match="Missing"):
        await verify_app_check(
            settings, get_firebase_app(settings), x_firebase_appcheck=None
        )


def test_emulator_host_from_settings_reaches_the_process_environment(monkeypatch):
    """.env values reach Settings only; firebase-admin reads os.environ (dev gotcha)."""
    import firebase_admin

    from recruitai.core.auth import get_firebase_app

    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(firebase_admin, "get_app", lambda: object())
    get_firebase_app(_settings(firebase_auth_emulator_host="emu:9099"))
    import os

    assert os.environ["FIREBASE_AUTH_EMULATOR_HOST"] == "emu:9099"
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST")
