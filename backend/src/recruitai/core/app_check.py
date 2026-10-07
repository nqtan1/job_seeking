"""Firebase App Check verification (ARCHITECTURE.md §4.5). Ready to use on AI-cost-relevant
endpoints as they land in P2 — not wired to every route yet, that's a per-endpoint decision.

Unlike ``core/auth.py``'s ID tokens, App Check has no emulator-mode shortcut in
firebase-admin: ``app_check.verify_token()`` always performs a real RS256 signature check
against Google's live JWKS endpoint (confirmed by reading the installed library — there is
no ``is_emulated()`` branch the way ``_token_gen.py`` has for ID tokens). There is no way to
produce a token that passes verification without a real Firebase project and a real
attestation provider (reCAPTCHA, Play Integrity, etc.) — the "valid token" test mocks
``app_check.verify_token`` itself, the same way P1-06 mocks ``ExpiredIdTokenError`` for a
case the Auth emulator can't produce.
"""

from typing import Annotated

import firebase_admin
from fastapi import Depends, Header
from firebase_admin import app_check
from starlette.concurrency import run_in_threadpool

from recruitai.config import Settings, get_settings
from recruitai.core.auth import get_firebase_app
from recruitai.core.errors import Unauthorized


async def verify_app_check(
    settings: Annotated[Settings, Depends(get_settings)],
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
    x_firebase_appcheck: Annotated[
        str | None, Header(alias="X-Firebase-AppCheck")
    ] = None,
) -> None:
    if settings.env == "local" and not settings.app_check_enforced:
        return
    if x_firebase_appcheck is None:
        raise Unauthorized("Missing X-Firebase-AppCheck header.")
    try:
        # Sync SDK call that fetches/verifies against a real JWKS endpoint over HTTP —
        # must not run on the event loop (checklist item 12, same reasoning as core/auth.py).
        await run_in_threadpool(app_check.verify_token, x_firebase_appcheck, app)
    except ValueError as exc:
        raise Unauthorized("Invalid or expired App Check token.") from exc
