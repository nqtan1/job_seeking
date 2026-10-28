"""Firebase ID token verification only (ARCHITECTURE.md §4.4, ADR 0007).

No DB access: provisioning is ``core/tenancy.py``'s job, so first login is one atomic transaction.
"""

import base64
import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Annotated

import firebase_admin
from fastapi import Depends, Header
from firebase_admin import auth as firebase_auth
from starlette.concurrency import run_in_threadpool

from recruitai.config import Settings, get_settings
from recruitai.core.errors import Forbidden, ReauthRequired, Unauthorized

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentUser:
    firebase_uid: str
    email: str
    email_verified: bool = False
    auth_time: int = 0  # epoch s of the original sign-in; unchanged by silent refresh


def get_firebase_app(
    settings: Annotated[Settings, Depends(get_settings)],
) -> firebase_admin.App:
    """One default app per process. In dev/test, ``FIREBASE_AUTH_EMULATOR_HOST`` (read
    directly by the firebase-admin/google-auth libraries, not by us) redirects every call
    to the emulator; no credentials file is needed either way for token *verification*."""
    # Those libraries only look at os.environ, but a .env file only reaches ``Settings``:
    # without this, ``fastapi dev`` + .env silently verifies against real Google (401 on
    # every emulator token).
    if settings.firebase_auth_emulator_host:
        os.environ.setdefault(
            "FIREBASE_AUTH_EMULATOR_HOST", settings.firebase_auth_emulator_host
        )
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(
            options={"projectId": settings.firebase_project_id}
        )


async def _verify(
    app: firebase_admin.App,
    settings: Settings,
    authorization: str | None,
    *,
    check_revoked: bool,
    max_age_s: int | None = None,
) -> CurrentUser:
    if authorization is None:
        raise Unauthorized("Missing Authorization header.")
    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not token:
        raise Unauthorized("Authorization header must be 'Bearer <token>'.")
    try:
        # Sync SDK call: verifies against Google's cached public certs over HTTP in
        # production (fetched/refreshed lazily), so it must not run on the event loop.
        claims = await run_in_threadpool(
            firebase_auth.verify_id_token, token, app=app, check_revoked=check_revoked
        )
    except Exception as exc:  # any verification failure -> 401, never leak why
        raise Unauthorized("The provided credentials are invalid or expired.") from exc
    email = claims.get("email")
    if not email:
        raise Unauthorized("Token has no email claim.")
    user = CurrentUser(
        firebase_uid=claims["uid"],
        email=email,
        email_verified=bool(claims.get("email_verified")),
        auth_time=int(claims.get("auth_time") or 0),
    )
    leeway = settings.auth_time_leeway_seconds
    age = time.time() - user.auth_time
    if age < -leeway or age > settings.session_absolute_days * 86400 + leeway:
        logger.info("reauth_required", extra={"reason": "absolute"})
        raise ReauthRequired(recent=False)
    if max_age_s is not None:
        if age > max_age_s + leeway:
            logger.info("step_up_fail")
            raise ReauthRequired(recent=True)
        logger.info("step_up_ok")
    return user


async def get_current_user(
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    return await _verify(app, settings, authorization, check_revoked=False)


async def get_current_user_strict(
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """For sensitive endpoints (account deletion, ADR 0007): also asks Firebase whether the
    token was revoked or the account disabled/deleted. One extra network call, so not the
    default: an ID token otherwise stays valid for up to an hour."""
    return await _verify(app, settings, authorization, check_revoked=True)


async def require_recent_auth(
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Step-up (ADR 0024): strict, and the sign-in itself must be at most
    ``stepup_max_age_seconds`` old. Otherwise ``401 reauth_required`` with ``recent=true``;
    the web app re-authenticates and retries."""
    return await _verify(
        app,
        settings,
        authorization,
        check_revoked=True,
        max_age_s=settings.stepup_max_age_seconds,
    )


def is_admin(user: CurrentUser, settings: Settings) -> bool:
    """Platform admin = a *verified* email listed in ``ADMIN_EMAILS``. Never from client input."""
    return user.email_verified and user.email.lower() in {
        e.lower() for e in settings.admin_emails
    }


async def require_admin(
    user: Annotated[CurrentUser, Depends(get_current_user_strict)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    if not is_admin(user, settings):
        raise Forbidden("Admin only.")
    return user


async def set_account_disabled(
    app: firebase_admin.App, firebase_uid: str, *, disabled: bool
) -> None:
    """Block or allow sign-in at Firebase. Blocking also revokes refresh tokens, so no new ID
    token can be minted; the already-issued one is refused by ``core/tenancy`` (blocked_at)."""

    def _apply() -> None:
        firebase_auth.update_user(firebase_uid, disabled=disabled, app=app)
        if disabled:
            firebase_auth.revoke_refresh_tokens(firebase_uid, app=app)

    await run_in_threadpool(_apply)


def _b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


async def warm_certs(settings: Settings) -> None:
    """Fetch Google's token-signing certificates now. The first ``verify_id_token`` of a process
    pays for that download (~0.5 s) in front of the first user's request; this makes it pay at
    startup, in parallel with the DB warm-up. The throwaway token is well-formed but unsigned, so
    it is always rejected after the certificates are cached. Best effort."""
    if (
        settings.firebase_auth_emulator_host
    ):  # the emulator has no certificates to fetch
        return
    pid = settings.firebase_project_id
    now = int(time.time())
    token = ".".join(
        (
            _b64({"alg": "RS256", "kid": "warm-up", "typ": "JWT"}),
            _b64(
                {
                    "aud": pid,
                    "iss": f"https://securetoken.google.com/{pid}",
                    "sub": "warm-up",
                    "iat": now,
                    "exp": now + 60,
                }
            ),
            "AAAA",
        )
    )
    with contextlib.suppress(Exception):  # rejection is the expected outcome
        await run_in_threadpool(
            firebase_auth.verify_id_token, token, app=get_firebase_app(settings)
        )
