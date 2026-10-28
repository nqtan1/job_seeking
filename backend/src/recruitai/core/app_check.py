"""Firebase App Check verification (ARCHITECTURE.md §4.5), applied per AI-cost endpoint.

firebase-admin has no emulator shortcut here, so tests mock ``app_check.verify_token``.
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
