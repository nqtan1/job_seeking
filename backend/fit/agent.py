from __future__ import annotations

from typing import Dict, Optional

from agents import BaseAgent, AgentConfig
from cv.schema import CVInformation
from fit.prompt import get_system_prompt_by_company_type
from fit.schema import FitCheck, InterviewPreparationKit
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

    def generate_interview_kit(
        self,
        candidate_cv: CVInformation,
        job_information: JobPosition,
        company_type: str,
        custom_context: Optional[str] = None,
        output_schema=InterviewPreparationKit,
    ) -> InterviewPreparationKit:
        """
        Generates a tailored interview prep kit with technical questions, behavioral queries, and a simulation prompt.
        """
        system_prompt = f"""
You are an elite, world-class technical recruiter and engineering coach with 20+ years of experience in talent development.
Your job is to generate a comprehensive, highly-tailored, and practical Mock Interview Preparation Kit for a candidate applying to a specific role.

The hiring company context is: {company_type} (Tailor your questions to this environment: e.g., speed, versatility, rapid prototyping for startup; scientific methodology, academic rigor, peer reviews for PhD; high scalability, enterprise systems, regulatory processes, architecture trade-offs for corporations).

Your generated kit must contain:
1. 3-5 Technical Questions: Focus on checking the candidate's gaps or exploring their deep technical experience as stated in their CV compared to the job requirements.
2. 2-3 Behavioral Questions: Frame them using situations appropriate for a {company_type} environment.
3. A detailed Simulation Prompt: A rich, custom prompt for the candidate to run an interactive mock interview with an AI assistant.

Make your questions and expected answers highly practical. Provide the candidate with true, valuable professional advice on how to stand out.
"""
        model = self.model.with_structured_output(output_schema)
        
        user_content = f"""
CANDIDATE CV:
{candidate_cv.model_dump_json(indent=2)}

JOB INFORMATION:
{job_information.model_dump_json(indent=2)}
"""
        if custom_context:
            user_content += f"\nADDITIONAL CONTEXT:\n{custom_context}"

        self.logger.info("Requesting Gemini to generate Interview prep kit for company_type=%s", company_type)
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])
        self.logger.info("Interview prep kit generation complete and response type=%s", type(response).__name__)
        return response
