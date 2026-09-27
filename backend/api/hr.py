from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from infrastructure.agents.agent_config import AgentConfig
from core.auth import TenantContext, get_tenant_context
from infrastructure.fit.agent import FitAgent
from infrastructure.hr.agent import HRRankingAgent
from domain.hr.schema import HRBatchRankingRequest, HRBatchRankingResult, HRJobStatusResponse, HRJobSubmission
from application.hr.service import HRRankingService
from utils.logger import get_logger
from workers.background import BackgroundJobStatus, get_background_job_manager, register_job_handler

logger = get_logger(name="hr.route", log_file="hr_api.log", level="INFO")

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent / "config/agent_config.yaml"
fit_agent = None


def _get_service() -> HRRankingService:
    global fit_agent
    active_agent = fit_agent
    if active_agent is None:
        active_agent = FitAgent(config=AgentConfig(config_path=CONFIG_PATH, section="hr"))
    return HRRankingService(agent=HRRankingAgent(fit_agent=active_agent))


def run_hr_batch_ranking(request: dict, tenant_context: dict) -> dict:
    """Registered durable background job handler for 'hr_batch_ranking'."""
    req_obj = HRBatchRankingRequest(**request)
    tenant_obj = TenantContext(**tenant_context)
    service = _get_service()
    result = service.rank_candidates(req_obj, tenant_obj)
    return result.model_dump()


# Register the durable job handler
register_job_handler("hr_batch_ranking", run_hr_batch_ranking)


@router.post("/rank")
async def rank_candidates(
    request: HRBatchRankingRequest,
    background: bool = Query(default=False, description="Queue the ranking job in the background"),
    tenant: TenantContext = Depends(get_tenant_context),
):
    logger.info(
        "rank_candidates called tenant=%s background=%s candidates=%s",
        tenant.tenant_id,
        background,
        len(request.candidates),
    )

    service = _get_service()
    if background:
        job_id = get_background_job_manager().submit(
            tenant_id=tenant.tenant_id,
            job_type="hr_batch_ranking",
            func=service.rank_candidates,
            request=request,
            tenant_context=tenant,
        )
        return HRJobSubmission(
            message="HR batch ranking queued",
            job_id=job_id,
            status=BackgroundJobStatus.QUEUED.value,
            tenant_id=tenant.tenant_id,
        ).model_dump()

    from starlette.concurrency import run_in_threadpool
    result = await run_in_threadpool(service.rank_candidates, request, tenant)
    return result.model_dump()


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, tenant: TenantContext = Depends(get_tenant_context)) -> HRJobStatusResponse:
    record = get_background_job_manager().get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if record.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=403, detail="You do not have access to this job")

    return HRJobStatusResponse(**record.to_dict())


@router.get("/context")
async def get_current_tenant(tenant: TenantContext = Depends(get_tenant_context)):
    return {
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.tenant_name,
        "is_authenticated": tenant.is_authenticated,
    }


@router.get("/formats")
async def get_supported_company_types():
    return {
        "company_types": ["startup", "phd", "corporation"],
        "background_job_statuses": [status.value for status in BackgroundJobStatus],
    }
