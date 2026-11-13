"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings, get_settings
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.errors import (
    NotFound,
    Unauthorized,
    UpstreamUnavailable,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.ratelimit import limit_ai, rate_limit
from recruitai.core.storage import Storage, get_storage_dependency
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.cvreview import service
from recruitai.modules.cvreview.models import CvReview
from recruitai.modules.cvreview.schemas import (
    CvReviewIn,
    CvReviewListItem,
    CvReviewOut,
    PdfLayoutOut,
    RecheckIn,
    RecheckOut,
    RunAccepted,
)


def require_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    if not settings.cv_review_enabled:
        raise UpstreamUnavailable(
            "CV review is switched off for now.", code="cv_review_disabled"
        )


router = APIRouter(
    prefix="/api/v1/cv-reviews",
    tags=["cvreview"],
    dependencies=[Depends(require_enabled)],
)
limit_recheck = rate_limit("cv_recheck", limit=120)  # a debounced editor, rules only
Ctx = Annotated[OrgContext, Depends(get_org_context)]
Db = Annotated[AsyncSession, Depends(get_db)]
Store = Annotated[Storage, Depends(get_storage_dependency)]


@router.post(
    "",
    status_code=202,
    response_model=RunAccepted,
    # Every review costs a model call: App Check applies (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def create_review(
    body: CvReviewIn,
    ctx: Ctx,
    db: Db,
    storage: Store,
) -> RunAccepted:
    """Queue a review; poll ``status_url``, then GET the review from the task's ``result_ref``."""
    task_id = await service.request_review(
        db, storage, org_id=ctx.org_id, user_id=ctx.user_id, payload=body
    )
    return RunAccepted(task_id=task_id, status_url=f"/api/v1/tasks/{task_id}")


@router.post(
    "/recheck",
    response_model=RecheckOut,
    dependencies=[Depends(limit_recheck)],
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def recheck(body: RecheckIn, _: Ctx) -> RecheckOut:
    return service.recheck(body)


@router.get(
    "", response_model=list[CvReviewListItem], responses=problem_responses(Unauthorized)
)
async def list_reviews(
    ctx: Ctx,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CvReview]:
    return await service.list_reviews(db, org_id=ctx.org_id, limit=limit, offset=offset)


@router.get(
    "/{review_id}",
    response_model=CvReviewOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def get_review(review_id: UUID, ctx: Ctx, db: Db) -> CvReview:
    return await service.get_review(db, org_id=ctx.org_id, review_id=review_id)


limit_pdf = rate_limit(
    "cv_pdf", limit=120
)  # a layout call and up to 10 page images per open


@router.get(
    "/{review_id}/layout",
    response_model=PdfLayoutOut,
    dependencies=[Depends(limit_pdf)],
    responses=problem_responses(Unauthorized, NotFound),
)
async def pdf_layout(
    review_id: UUID, ctx: Ctx, db: Db, storage: Store
) -> dict[str, Any]:
    """Where each block sits in the original PDF (404 ``cv_no_pdf`` for DOCX/text uploads)."""
    return await service.pdf_layout(db, storage, org_id=ctx.org_id, review_id=review_id)


@router.get(
    "/{review_id}/pages/{page}",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        **problem_responses(Unauthorized, NotFound),
    },
    dependencies=[Depends(limit_pdf)],
)
async def pdf_page(
    review_id: UUID,
    page: Annotated[int, Path(ge=1, le=10)],
    ctx: Ctx,
    db: Db,
    storage: Store,
) -> Response:
    png = await service.pdf_page(
        db, storage, org_id=ctx.org_id, review_id=review_id, page=page
    )
    return Response(
        png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.delete(
    "/{review_id}", status_code=204, responses=problem_responses(Unauthorized, NotFound)
)
async def delete_review(review_id: UUID, ctx: Ctx, db: Db) -> Response:
    await service.delete_review(db, org_id=ctx.org_id, review_id=review_id)
    return Response(status_code=204)
