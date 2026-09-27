from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends

from infrastructure.agents.agent_config import AgentConfig
from infrastructure.career_chat.agent import CareerChatAgent
from domain.career_chat.schema import CareerChatRequest, CareerChatResponse
from application.career_chat.service import CareerChatService
from utils.logger import get_logger
from core.auth import TenantContext, get_tenant_context

logger = get_logger(name="career_chat.route", log_file="career_chat_api.log", level="INFO")

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent / "config/agent_config.yaml"
agent = None


def _get_service() -> CareerChatService:
    global agent
    active_agent = agent
    if active_agent is None:
        active_agent = CareerChatAgent(config=AgentConfig(config_path=CONFIG_PATH, section="career_chat"))
    return CareerChatService(agent=active_agent)


@router.post("/message", response_model=CareerChatResponse)
async def send_career_chat_message(
    request: CareerChatRequest, tenant: TenantContext = Depends(get_tenant_context)
) -> CareerChatResponse:
    logger.info(
        "send_career_chat_message called candidate=%s has_job=%s",
        request.candidate_cv.personal_info.name,
        bool(request.job_information),
    )

    try:
        return await _get_service().send_message(request, tenant_id=tenant.tenant_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Career chat message failed: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get a reply from the career coach")
