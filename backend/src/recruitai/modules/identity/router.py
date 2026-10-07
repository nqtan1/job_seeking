"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated
from uuid import UUID

import firebase_admin
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import overrides
from recruitai.config import Settings, get_settings
from recruitai.core.auth import (
    CurrentUser,
    get_current_user,
    get_firebase_app,
    is_admin,
    require_admin,
    set_account_disabled,
)
from recruitai.core.db import get_db
from recruitai.core.errors import (
    Forbidden,
    NotFound,
    Unauthorized,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.identity import service
from recruitai.modules.identity.schemas import (
    AdminStats,
    AdminUserList,
    AdminUserOut,
    AiConsoleOut,
    AiOverrideIn,
    MeResponse,
    OnboardingOut,
    PreferencesIn,
    UserOut,
)

router = APIRouter(prefix="/api/v1", tags=["identity"])


@router.get(
    "/me",
    response_model=MeResponse,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_me(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeResponse:
    result = await service.get_me(db, ctx)
    return MeResponse(
        user=UserOut(
            id=result.user_id, email=result.email, display_name=result.display_name
        ),
        active_org_id=result.active_org_id,
        onboarding=OnboardingOut(has_profile=result.has_profile),
        is_admin=is_admin(current, settings),
        email_reminders=result.email_reminders,
    )


@router.patch(
    "/me/preferences",
    status_code=204,
    responses=problem_responses(Unauthorized),
)
async def update_preferences(
    body: PreferencesIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.set_email_reminders(
        db, user_id=ctx.user_id, enabled=body.email_reminders
    )
    return Response(status_code=204)


admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@admin_router.get(
    "/users",
    response_model=AdminUserList,
    responses=problem_responses(Unauthorized, Forbidden),
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[
        str | None, Query(max_length=100, description="Email contains")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserList:
    users, total = await service.list_users(db, q=q, limit=limit, offset=offset)
    return AdminUserList(
        items=[
            AdminUserOut(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                created_at=u.created_at,
                last_active_at=u.last_active_at,
                blocked=u.blocked_at is not None,
            )
            for u in users
        ],
        total=total,
    )


@admin_router.get(
    "/stats",
    response_model=AdminStats,
    responses=problem_responses(Unauthorized, Forbidden),
)
async def stats(db: Annotated[AsyncSession, Depends(get_db)]) -> AdminStats:
    return AdminStats.model_validate(await service.platform_stats(db))


async def _set_blocked(
    user_id: UUID,
    blocked: bool,
    admin: CurrentUser,
    settings: Settings,
    db: AsyncSession,
    app: firebase_admin.App,
) -> Response:
    target = await service.set_blocked(
        db,
        admin_uid=admin.firebase_uid,
        admin_emails=settings.admin_emails,
        target_id=user_id,
        blocked=blocked,
    )
    await set_account_disabled(app, target.firebase_uid, disabled=blocked)
    return Response(status_code=204)


_BLOCK_ERRORS = problem_responses(Unauthorized, Forbidden, NotFound, ValidationFailed)


@admin_router.post("/users/{user_id}/block", status_code=204, responses=_BLOCK_ERRORS)
async def block_user(
    user_id: UUID,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
) -> Response:
    """Refuse every request of this user at once and stop them signing in again."""
    return await _set_blocked(user_id, True, admin, settings, db, app)


@admin_router.post("/users/{user_id}/unblock", status_code=204, responses=_BLOCK_ERRORS)
async def unblock_user(
    user_id: UUID,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
) -> Response:
    return await _set_blocked(user_id, False, admin, settings, db, app)


@admin_router.get(
    "/ai",
    response_model=AiConsoleOut,
    responses=problem_responses(Unauthorized, Forbidden),
)
async def ai_console(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AiConsoleOut:
    """Per AI feature: model in use, prompt version, calls, errors, latency and tokens (30 days),
    plus the allowed models and the change history. No prompts, no user content."""
    return AiConsoleOut.model_validate(await service.ai_console(db, settings))


@admin_router.put(
    "/ai/{feature}",
    status_code=204,
    responses=problem_responses(Unauthorized, Forbidden, NotFound, ValidationFailed),
)
async def set_ai_override(
    feature: str,
    body: AiOverrideIn,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Use another allowed model for one feature, without a deploy. Audited."""
    await overrides.set_override(
        db,
        settings,
        feature=feature,
        provider=body.provider,
        model=body.model,
        admin_user_id=await service.admin_user_id(db, admin.firebase_uid),
    )
    return Response(status_code=204)


@admin_router.delete(
    "/ai/{feature}",
    status_code=204,
    responses=problem_responses(Unauthorized, Forbidden, NotFound),
)
async def clear_ai_override(
    feature: str,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Back to the config.yaml default for this feature. Audited."""
    await overrides.clear_override(
        db,
        feature=feature,
        admin_user_id=await service.admin_user_id(db, admin.firebase_uid),
    )
    return Response(status_code=204)
