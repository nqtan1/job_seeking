"""Signed, single-purpose, expiring "stop radars" links for e-mails (ADR 0024).

``token = b64url(payload) . b64url(HMAC-SHA256(secret, payload))``. The payload names one org/user
and an expiry; the only thing it can ever do is withdraw that org's radar consent. It carries no
session and grants nothing else. Verification is constant-time and fails closed."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class LinkClaims:
    org_id: UUID
    user_id: UUID


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, payload: bytes) -> bytes:
    return hmac.new(secret.encode(), payload, hashlib.sha256).digest()


def sign(
    secret: str, *, org_id: UUID, user_id: UUID, ttl_s: int, now: float | None = None
) -> str:
    assert secret, "a link needs a secret"
    payload = json.dumps(
        {
            "o": str(org_id),
            "u": str(user_id),
            "e": int((now if now is not None else time.time()) + ttl_s),
        },
        separators=(",", ":"),
    ).encode()
    return f"{_b64(payload)}.{_b64(_mac(secret, payload))}"


def verify(secret: str, token: str, *, now: float | None = None) -> LinkClaims | None:
    """The claims, or ``None`` for anything wrong (bad shape, bad MAC, expired)."""
    if not secret:
        return None
    try:
        body, _, sig = token.partition(".")
        payload = _unb64(body)
        if not hmac.compare_digest(_unb64(sig), _mac(secret, payload)):
            return None
        data = json.loads(payload)
        if data["e"] < (now if now is not None else time.time()):
            return None
        return LinkClaims(UUID(data["o"]), UUID(data["u"]))
    except Exception:  # noqa: BLE001  (any parse failure is just "invalid")
        return None
