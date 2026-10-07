"""HTTP only: parse the request, call the service, map the result to a response schema."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
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
from recruitai.core.ratelimit import limit_ai
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.jobs.providers.base import JobProvider
from recruitai.modules.jobs.providers.factory import france_travail_provider
from recruitai.modules.radar import service
from recruitai.modules.radar.models import RadarRun, RadarSearch
from recruitai.modules.radar.schemas import (
    AiUseOut,
    Highlights,
    InsightsOut,
    KeepOut,
    RadarResultOut,
    RadarRunOut,
    RadarSearchIn,
    RadarSearchOut,
    RadarSearchUpdate,
    RadarStatusOut,
    ResultStatus,
    RunAccepted,
)

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])


def get_provider() -> JobProvider:
    return france_travail_provider()


def _run_out(r: RadarRun) -> RadarRunOut:
    return RadarRunOut.model_validate(
        {
            "id": r.id,
            "search_id": r.search_id,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "status": r.status,
            "stop_reason": r.stop_reason,
            "found": r.found,
            "added": r.added,
            "scored": r.scored,
            "shortlisted": r.shortlisted,
        }
    )


def _search_out(s: RadarSearch) -> RadarSearchOut:
    return RadarSearchOut.model_validate(
        {
            "id": s.id,
            "name": s.name,
            "query": s.query,
            "department": s.department,
            "contract_type": s.contract_type,
            "min_score": s.min_score,
            "daily_limit": s.daily_limit,
            "enabled": s.enabled,
            "last_run_at": s.last_run_at,
            "created_at": s.created_at,
        }
    )


@router.post(
    "/searches",
    status_code=201,
    response_model=RadarSearchOut,
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def create_search(
    body: RadarSearchIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RadarSearchOut:
    return _search_out(await service.create_search(db, org_id=ctx.org_id, data=body))


@router.get(
    "/searches",
    response_model=list[RadarSearchOut],
    responses=problem_responses(Unauthorized),
)
async def list_searches(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RadarSearchOut]:
    return [_search_out(s) for s in await service.list_searches(db, org_id=ctx.org_id)]


@router.patch(
    "/searches/{search_id}",
    response_model=RadarSearchOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def update_search(
    search_id: UUID,
    body: RadarSearchUpdate,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RadarSearchOut:
    return _search_out(
        await service.update_search(
            db, org_id=ctx.org_id, search_id=search_id, changes=body
        )
    )


@router.delete(
    "/searches/{search_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def delete_search(
    search_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.delete_search(db, org_id=ctx.org_id, search_id=search_id)
    return Response(status_code=204)


@router.post(
    "/searches/{search_id}/run",
    status_code=202,
    response_model=RunAccepted,
    # A run costs model calls (fit analyses), so App Check applies (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def run_search(
    search_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunAccepted:
    """Queue a run; poll ``status_url``. The radar only searches and scores: it never applies."""
    if not settings.radar_enabled:
        raise UpstreamUnavailable(
            "The job radar is switched off for now.", code="radar_disabled"
        )
    task_id = await service.request_run(
        db, org_id=ctx.org_id, user_id=ctx.user_id, search_id=search_id
    )
    return RunAccepted(task_id=task_id, status_url=f"/api/v1/tasks/{task_id}")


@router.get(
    "/results",
    response_model=list[RadarResultOut],
    responses=problem_responses(Unauthorized),
)
async def list_results(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: ResultStatus | None = "new",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RadarResultOut]:
    views = await service.list_results(
        db, org_id=ctx.org_id, status=status, limit=limit, offset=offset
    )
    return [
        RadarResultOut(
            id=v.result.id,
            search_id=v.result.search_id,
            search_name=v.search_name,
            job_id=v.result.job_id,
            score=v.result.score,
            status=v.result.status,  # type: ignore[arg-type]  # DB CHECK limits the values
            found_at=v.result.found_at,
            title=v.title,
            company=v.company,
            highlights=Highlights.model_validate(v.result.highlights or {}),
            application_status=v.application_status,
        )
        for v in views
    ]


@router.post(
    "/results/{result_id}/approve",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def approve_result(
    result_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.approve(db, org_id=ctx.org_id, result_id=result_id)
    return Response(status_code=204)


@router.post(
    "/results/{result_id}/dismiss",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def dismiss_result(
    result_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.dismiss(db, org_id=ctx.org_id, result_id=result_id)
    return Response(status_code=204)


@router.post(
    "/results/seen", status_code=204, responses=problem_responses(Unauthorized)
)
async def mark_results_seen(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.mark_seen(db, org_id=ctx.org_id)
    return Response(status_code=204)


@router.get(
    "/runs",
    response_model=list[RadarRunOut],
    responses=problem_responses(Unauthorized),
)
async def list_runs(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[RadarRunOut]:
    return [
        _run_out(r) for r in await service.list_runs(db, org_id=ctx.org_id, limit=limit)
    ]


@router.get(
    "/usage",
    response_model=AiUseOut,
    responses=problem_responses(Unauthorized),
)
async def ai_use(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AiUseOut:
    """Today's AI calls against the daily quota, and where the radar stops (it leaves some
    calls free for the user's own chat and letters)."""
    used, quota, stops = await service.ai_use_today(
        db, user_id=ctx.user_id, quota=settings.ai_daily_quota_per_user
    )
    return AiUseOut(used=used, quota=quota, radar_stops_at=stops)


@router.get(
    "/status",
    response_model=RadarStatusOut,
    responses=problem_responses(Unauthorized),
)
async def radar_status(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RadarStatusOut:
    """At a glance: new matches, whether a run is going on, the last run and the next one."""
    data = await service.status(db, org_id=ctx.org_id, now=datetime.now(UTC))
    return RadarStatusOut.model_validate(
        {**data, "last_run": _run_out(data["last_run"]) if data["last_run"] else None}
    )


@router.get(
    "/insights",
    response_model=InsightsOut,
    responses=problem_responses(Unauthorized),
)
async def insights(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InsightsOut:
    """The last 30 days: scored, kept, approved, applied, interviews, and what is missing most."""
    return InsightsOut.model_validate(
        await service.insights(db, org_id=ctx.org_id, now=datetime.now(UTC))
    )


@router.post(
    "/results/{result_id}/keep",
    response_model=KeepOut,
    responses=problem_responses(Unauthorized, NotFound, UpstreamUnavailable),
)
async def keep_result(
    result_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider: Annotated[JobProvider, Depends(get_provider)],
) -> KeepOut:
    """ "Review anyway": put a job the radar did not shortlist into the user's jobs. No AI call."""
    job_id = await service.keep_anyway(
        db, provider, org_id=ctx.org_id, result_id=result_id
    )
    return KeepOut(job_id=job_id)
