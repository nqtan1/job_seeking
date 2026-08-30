from __future__ import annotations

from typing import Dict, Optional

from agents import BaseAgent, AgentConfig
from cv.schema import CVInformation
from fit.prompt import get_system_prompt_by_company_type
from fit.schema import FitCheck
from jobs.schema import JobPosition
from langchain_core.messages import HumanMessage, SystemMessage


class FitAgent(BaseAgent):
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        logger_name: str = "fit.agent",
        log_file: str = "fit_api.log",
        log_level: str = "INFO",
    ):
        super().__init__(
            config,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level,
        )
        self.logger.info(
            "FitAgent initialized with provider=%s api_key_set=%s",
            self.config.provider,
            bool(self.config.api_key),
        )

    def _build_user_message(
        self,
        candidate_cv: CVInformation,
        job_information: JobPosition,
        recruiter_attend: Optional[Dict] = None,
        custom_context: Optional[str] = None,
    ) -> HumanMessage:
        message = f"""
Compare this candidate CV against the job description and return a structured fit assessment.

CANDIDATE CV:
{candidate_cv.model_dump_json(indent=2)}

JOB INFORMATION:
{job_information.model_dump_json(indent=2)}
"""

        if recruiter_attend:
            message += f"""

RECRUITER CONDITIONS:
{recruiter_attend}
"""

        if custom_context:
            message += f"""

ADDITIONAL CONTEXT:
{custom_context}
"""

        return HumanMessage(content=message)

    def analyze_fit(
        self,
        candidate_cv: CVInformation,
        job_information: JobPosition,
        company_type: str,
        output_schema=FitCheck,
        recruiter_attend: Optional[Dict] = None,
        custom_context: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> FitCheck:
        if system_prompt is None:
            system_prompt = get_system_prompt_by_company_type(company_type)

        model = self.model.with_structured_output(output_schema) if output_schema else self.model
        message = self._build_user_message(
            candidate_cv=candidate_cv,
            job_information=job_information,
            recruiter_attend=recruiter_attend,
            custom_context=custom_context,
        )

        response = model.invoke([
            SystemMessage(content=system_prompt),
            message,
        ])
        self.logger.info("Fit analysis completed and response type=%s", type(response).__name__)
        return response

