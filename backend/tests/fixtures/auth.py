"""Firebase-emulator token helper. Talks to the emulator's REST API directly, independent
of our own ``core/auth.py``."""

import os
import uuid
from collections.abc import Callable

import httpx
import pytest

_BASE = "identitytoolkit.googleapis.com/v1"
_API_KEY = "fake-api-key"
_PROJECT = os.environ.get("FIREBASE_PROJECT_ID", "demo-recruitai")


def _host() -> str:
    return os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")


def mint_emulator_token(
    uid: str, email: str, password: str = "test-password-123"
) -> str:
    """Create the user with the given uid in the emulator (idempotent) and return a real ID token."""
    base = f"http://{_host()}/{_BASE}"
    created = httpx.post(
        f"{base}/projects/{_PROJECT}/accounts",
        headers={"Authorization": "Bearer owner"},
        json={"localId": uid, "email": email, "password": password},
        timeout=10,
    )
    if (
        created.status_code != 200
        and "DUPLICATE" not in created.text
        and "EXISTS" not in created.text
    ):
        created.raise_for_status()
    signed_in = httpx.post(
        f"{base}/accounts:signInWithPassword",
        params={"key": _API_KEY},
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=10,
    )
    signed_in.raise_for_status()
    token: str = signed_in.json()["idToken"]
    return token


@pytest.fixture
def emulator_token() -> Callable[[str, str], str]:
    return mint_emulator_token


@pytest.fixture
def two_tenant_tokens() -> tuple[str, str]:
    """Two distinct users for cross-tenant tests (every module needs one)."""
    tag = uuid.uuid4().hex[:8]
    a = mint_emulator_token(f"uid-a-{tag}", f"a-{tag}@example.test")
    b = mint_emulator_token(f"uid-b-{tag}", f"b-{tag}@example.test")
    return a, b
