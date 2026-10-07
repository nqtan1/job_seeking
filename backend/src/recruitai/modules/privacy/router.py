"""HTTP only. ``/api/v1/me/export`` lives here, next to ``/api/v1/me`` in identity."""

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
    get_current_user_strict,
    get_firebase_app,
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
    # Sensitive: the archive holds everything, so a revoked token is refused (ADR 0007).
    _current_user: Annotated[CurrentUser, Depends(get_current_user_strict)],
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskAccepted:
    """Queue an export of everything the account holds (JSON + the original files, as a
    ZIP). Poll ``status_url``: when ``done`` it carries a signed ``download_url``; the archive
    is kept until the next export replaces it (and is swept after 24 h)."""
    task_id = await service.request_export(db, org_id=ctx.org_id, user_id=ctx.user_id)
    return TaskAccepted(task_id=task_id, status_url=f"/api/v1/tasks/{task_id}")


@router.delete(
    "",
    status_code=204,
    responses=problem_responses(Unauthorized, UpstreamUnavailable, RateLimited),
    dependencies=[Depends(limit_sensitive)],
)
async def delete_my_account(
    # Sensitive: the token is also checked against revocation (ADR 0007).
    current_user: Annotated[CurrentUser, Depends(get_current_user_strict)],
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
