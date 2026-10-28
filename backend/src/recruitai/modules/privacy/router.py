"""HTTP only. ``/api/v1/me/export`` lives here, next to ``/api/v1/me`` in identity."""

import logging
from typing import Annotated
from uuid import UUID

import firebase_admin
from fastapi import APIRouter, Depends, Response
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from recruitai.core.auth import (
    CurrentUser,
    get_firebase_app,
    require_recent_auth,
)
from recruitai.core.db import get_db
from recruitai.core.errors import (
    Unauthorized,
    UpstreamUnavailable,
    problem_responses,
)
from recruitai.core.ratelimit import RateLimited, limit_sensitive
from recruitai.core.storage import Storage, get_storage_dependency
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.privacy import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/me", tags=["privacy"])


class TaskAccepted(BaseModel):
    task_id: UUID
    status_url: str


@router.post(
    "/export",
    status_code=202,
    response_model=TaskAccepted,
    responses=problem_responses(Unauthorized, RateLimited),
    dependencies=[Depends(limit_sensitive)],
)
async def export_my_data(
    # Sensitive: the archive holds everything: revoked or stale sign-in is refused (ADR 0024).
    _current_user: Annotated[CurrentUser, Depends(require_recent_auth)],
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskAccepted:
    """Queue an export of everything the account holds (JSON + original files, ZIP). Poll
    ``status_url``; when ``done`` it carries a signed ``download_url``. Kept until replaced or 24 h."""
    task_id = await service.request_export(db, org_id=ctx.org_id, user_id=ctx.user_id)
    return TaskAccepted(task_id=task_id, status_url=f"/api/v1/tasks/{task_id}")


@router.delete(
    "",
    status_code=204,
    responses=problem_responses(Unauthorized, UpstreamUnavailable, RateLimited),
    dependencies=[Depends(limit_sensitive)],
)
async def delete_my_account(
    # Sensitive: revocation + recent sign-in (step-up, ADR 0024).
    current_user: Annotated[CurrentUser, Depends(require_recent_auth)],
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
) -> Response:
    """Delete the account and all its data, immediately and for good: database rows, queued
    jobs, every stored file, and the sign-in identity itself. Cannot be undone."""

    async def delete_identity() -> None:
        try:
            await run_in_threadpool(
                firebase_auth.delete_user, current_user.firebase_uid, app=app
            )
        except firebase_auth.UserNotFoundError:
            return  # already gone: that is the goal
        except Exception as exc:
            raise UpstreamUnavailable(
                "Your data was deleted, but removing your sign-in failed. Try again.",
                code="account_deletion_incomplete",
            ) from exc

    await service.delete_account(
        db, storage, user_id=ctx.user_id, delete_identity=delete_identity
    )
    return Response(status_code=204)


@router.post(
    "/sessions/revoke",
    status_code=204,
    responses=problem_responses(Unauthorized, UpstreamUnavailable, RateLimited),
    dependencies=[Depends(limit_sensitive)],
)
async def sign_out_everywhere(
    current_user: Annotated[CurrentUser, Depends(require_recent_auth)],
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
) -> Response:
    """Revoke every refresh token of the account. An issued ID token lives up to 1 h; sensitive
    endpoints refuse it at once."""
    try:
        await run_in_threadpool(
            firebase_auth.revoke_refresh_tokens, current_user.firebase_uid, app=app
        )
    except Exception as exc:
        raise UpstreamUnavailable(
            "Could not sign out other devices. Try again."
        ) from exc
    logger.info("revoke_all")
    return Response(status_code=204)
