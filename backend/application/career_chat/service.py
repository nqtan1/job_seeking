from __future__ import annotations

from langchain_core.messages import HumanMessage, AIMessage
from starlette.concurrency import run_in_threadpool

from infrastructure.career_chat.agent import CareerChatAgent
from domain.career_chat.schema import CareerChatRequest, CareerChatResponse
from utils.logger import get_logger


class CareerChatService:
    def __init__(self, agent: CareerChatAgent, logger_name: str = "career_chat.service"):
        self.agent = agent
        self.logger = get_logger(name=logger_name, log_file="career_chat_api.log", level="INFO")

    async def send_message(
        self, request: CareerChatRequest, tenant_id: str = "default-tenant"
    ) -> CareerChatResponse:
        self.logger.info(
            "Career chat message received",
            extra={
                "tenant_id": tenant_id,
                "candidate": request.candidate_cv.personal_info.name,
                "has_job": bool(request.job_information),
                "history_len": len(request.history),
            },
        )

        self.agent.seed_context(
            candidate_cv=request.candidate_cv,
            job_information=request.job_information,
            fit_check=request.fit_check,
            interview_kit=request.interview_kit,
        )

        for turn in request.history:
            if turn.role == "user":
                self.agent.conversation_history.append(HumanMessage(content=turn.content))
            else:
                self.agent.conversation_history.append(AIMessage(content=turn.content))

        reply = await run_in_threadpool(self.agent.reply, request.message)

        return CareerChatResponse(reply=reply)
