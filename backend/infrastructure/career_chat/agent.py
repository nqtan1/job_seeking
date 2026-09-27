from __future__ import annotations

from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

from infrastructure.agents.base_agents import BaseAgent
from infrastructure.agents.agent_config import AgentConfig
from infrastructure.career_chat.prompt import SYSTEM_PROMPT_CAREER_COACH, SUMMARIZE_PROMPT
from domain.cv.schema import CVInformation
from domain.jobs.schema import JobPosition
from domain.fit.schema import FitCheck, InterviewPreparationKit

# How many of the most recent conversational messages to keep verbatim when the
# history needs condensing; everything older gets folded into one summary message.
RECENT_TURNS_KEPT = 6


class CareerChatAgent(BaseAgent):
    """
    Stateless-per-request chat agent that answers a candidate's questions about a
    job, their CV, and their career, grounded in already-computed context (CV, job
    description, fit analysis, interview kit).
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        logger_name: str = "career_chat.agent",
        log_file: str = "career_chat_api.log",
        log_level: str = "INFO",
    ):
        super().__init__(
            config,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level,
        )

    def seed_context(
        self,
        candidate_cv: CVInformation,
        job_information: Optional[JobPosition] = None,
        fit_check: Optional[FitCheck] = None,
        interview_kit: Optional[InterviewPreparationKit] = None,
    ) -> None:
        """Reset the conversation and seed it with the candidate's current context."""
        context = f"""
CANDIDATE CV:
{candidate_cv.model_dump_json(indent=2)}
"""
        if job_information:
            context += f"""

JOB UNDER DISCUSSION:
{job_information.model_dump_json(indent=2)}
"""
        if fit_check:
            context += f"""

PREVIOUS FIT ANALYSIS:
{fit_check.model_dump_json(indent=2)}
"""
        if interview_kit:
            context += f"""

MOCK INTERVIEW KIT ALREADY PREPARED:
{interview_kit.model_dump_json(indent=2)}
"""
        self.conversation_history = [
            SystemMessage(content=SYSTEM_PROMPT_CAREER_COACH + "\n" + context)
        ]
        self.logger.info(
            "Career chat context seeded",
            extra={
                "has_job": bool(job_information),
                "has_fit_check": bool(fit_check),
                "has_interview_kit": bool(interview_kit),
            },
        )

    def reply(self, message: str) -> str:
        """Send a candidate message and return the coach's reply as plain text."""
        return self.chat_as_string(message)

    def _truncate_history_smart(self) -> None:
        """
        Condense older turns into one summary message instead of dropping them, so a
        long chat with a small-context local model doesn't silently lose earlier
        context. Falls back to the parent's plain truncation if summarization fails
        or there isn't enough history yet to make summarizing worthwhile.
        """
        if len(self.conversation_history) <= self.config.max_history:
            return

        system_msgs = [m for m in self.conversation_history if isinstance(m, SystemMessage)]
        conversation_msgs = [m for m in self.conversation_history if not isinstance(m, SystemMessage)]

        if len(conversation_msgs) <= RECENT_TURNS_KEPT:
            super()._truncate_history_smart()
            return

        to_summarize = conversation_msgs[:-RECENT_TURNS_KEPT]
        recent = conversation_msgs[-RECENT_TURNS_KEPT:]

        try:
            transcript = "\n".join(f"{m.__class__.__name__}: {m.content}" for m in to_summarize)
            summary_response = self.model.invoke([
                SystemMessage(content=SUMMARIZE_PROMPT),
                HumanMessage(content=transcript),
            ])
            summary_msg = SystemMessage(content=f"Earlier conversation summary:\n{summary_response.content}")
            original_size = len(self.conversation_history)
            self.conversation_history = system_msgs + [summary_msg] + recent
            self.logger.info(
                "Career chat history condensed via summarization from %s to %s messages",
                original_size,
                len(self.conversation_history),
            )
        except Exception as exc:
            self.logger.warning(
                "Career chat history summarization failed, falling back to plain truncation: %s",
                str(exc),
            )
            super()._truncate_history_smart()
