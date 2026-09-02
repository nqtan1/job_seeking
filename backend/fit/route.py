from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends

from agents.agent_config import AgentConfig
from fit.agent import FitAgent
from fit.schema import FitAnalysisRequest, FitAnalysisResponse, FitCheck
from fit.service import FitService
from utils.logger import get_logger
from core.auth import TenantContext, get_tenant_context

logger = get_logger(name="fit.route", log_file="fit_api.log", level="INFO")

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent / "config/agent_config.yaml"
agent = None


def _get_service() -> FitService:
	global agent
	active_agent = agent
	if active_agent is None:
		active_agent = FitAgent(config=AgentConfig(config_path=CONFIG_PATH))
	return FitService(agent=active_agent)


@router.post("/analyze", response_model=FitAnalysisResponse)
async def analyze_fit(request: FitAnalysisRequest, tenant: TenantContext = Depends(get_tenant_context)) -> FitAnalysisResponse:
	logger.info(
		"analyze_fit called candidate=%s company=%s company_type=%s",
		request.candidate_cv.personal_info.name,
		request.job_information.company,
		request.company_type,
	)

	try:
		return await _get_service().analyze_fit(request, tenant_id=tenant.tenant_id)
	except HTTPException:
		raise
	except Exception as exc:
		logger.error("Fit analysis failed: %s", str(exc), exc_info=True)
		raise HTTPException(status_code=500, detail="Failed to analyze fit")


@router.get("/formats")
async def get_supported_company_types():
	return {
		"company_types": ["startup", "phd", "corporation"],
		"supported_output": FitCheck.__name__,
	}
