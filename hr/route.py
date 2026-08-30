from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from agents.agent_config import AgentConfig
from core.auth import TenantContext, get_tenant_context
from fit.agent import FitAgent
from hr.agent import HRRankingAgent
from hr.schema import HRBatchRankingRequest, HRBatchRankingResult, HRJobStatusResponse, HRJobSubmission
from hr.service import HRRankingService
from utils.logger import get_logger
from workers.background import BackgroundJobStatus, get_background_job_manager

logger = get_logger(name="hr.route", log_file="hr_api.log", level="INFO")

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent / "config/agent_config.yaml"
fit_agent = None


def _get_service() -> HRRankingService:
    global fit_agent
    active_agent = fit_agent
    if active_agent is None:
        active_agent = FitAgent(config=AgentConfig(config_path=CONFIG_PATH))
    return HRRankingService(agent=HRRankingAgent(fit_agent=active_agent))


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

    result = service.rank_candidates(request, tenant)
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