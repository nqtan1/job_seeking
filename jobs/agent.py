import base64
import time
from pathlib import Path
from typing import Optional, Sequence, Union

from agents import BaseAgent, AgentConfig
from google import genai
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from jobs.schema import JobPosition


class JobExtractionAgent(BaseAgent):

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        logger_name: str = "jobs.agent",
        log_file: str = "jobs_api.log",
        log_level: str = "DEBUG",
    ):
        super().__init__(
            config,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level,
        )
        self.logger.debug(
            "JobExtractionAgent initialized with provider=%s api_key_set=%s",
            self.config.provider,
            bool(self.config.api_key),
        )
        self.client = genai.Client(api_key=self.config.api_key) if self.config.provider == "api_key" else None

    def _get_mime_type(self, file_path: Union[str, Path]) -> str:
        ext = Path(file_path).suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".img": "application/octet-stream",
        }
        mime_type = mime_types.get(ext, "application/octet-stream")
        self.logger.debug("Detected mime_type=%s for file_path=%s", mime_type, file_path)
        return mime_type

    def _normalize_file_paths(
        self,
        file_path: Union[str, Path, Sequence[Union[str, Path]]],
    ) -> list[Path]:
        if isinstance(file_path, (str, Path)):
            return [Path(file_path)]
        return [Path(path) for path in file_path]

    def _build_text_message(self, message: str, job_text: str) -> HumanMessage:
        self.logger.debug("Job extraction using raw text input")
        return HumanMessage(
            content=[
                {"type": "text", "text": message},
                {"type": "text", "text": f"Job Description:\n{job_text}"},
            ]
        )

    def _wait_for_uploaded_file(self, file):
        while file.state.name == "PROCESSING":
            self.logger.debug("Job file still processing: %s", file.name)
            time.sleep(2)
            file = self.client.files.get(name=file.name)
        return file

    def _build_gemini_file_message(
        self,
        file_paths: Sequence[Path],
        message: str,
    ) -> HumanMessage:
        if not self.client:
            raise RuntimeError("Gemini API client is not initialized for api_key mode")

        self.logger.debug("Job extraction using Gemini file upload mode")
        content = [{"type": "text", "text": message}]

        for fpath in file_paths:
            self.logger.debug("Uploading job file: %s", fpath)
            file = self.client.files.upload(file=str(fpath))
            file = self._wait_for_uploaded_file(file)

            mime_type = self._get_mime_type(fpath)
            self.logger.debug("Job file ready uri=%s mime_type=%s", file.uri, mime_type)
            content.append(
                {
                    "type": "file",
                    "file_id": file.uri,
                    "mime_type": mime_type,
                }
            )

        self.logger.debug("Job extraction message assembled with %s file blocks", len(content) - 1)
        return HumanMessage(content=content)

    def _build_vertex_file_message(
        self,
        file_paths: Sequence[Path],
        message: str,
    ) -> HumanMessage:
        self.logger.debug("Job extraction using Vertex base64 mode")
        content = [{"type": "text", "text": message}]

        for fpath in file_paths:
            mime_type = self._get_mime_type(fpath)
            file_data = base64.b64encode(fpath.read_bytes()).decode("utf-8")
            self.logger.debug(
                "Encoded job file for vertex path=%s mime_type=%s bytes=%s",
                fpath,
                mime_type,
                len(file_data),
            )
            content.append(
                {
                    "type": "file",
                    "source_type": "base64",
                    "mime_type": mime_type,
                    "data": file_data,
                }
            )

        self.logger.debug("Job extraction message assembled with %s file blocks", len(content) - 1)
        return HumanMessage(content=content)

    def _build_file_message(
        self,
        file_paths: Sequence[Path],
        message: str,
    ) -> HumanMessage:
        if self.config.provider == "api_key":
            return self._build_gemini_file_message(file_paths, message)
        return self._build_vertex_file_message(file_paths, message)

    def extract_job(
        self,
        file_path: Optional[Union[str, Path, Sequence[Union[str, Path]]]] = None,
        job_text: Optional[str] = None,
        message: Optional[str] = None,
        output_schema: Optional[BaseModel] = None,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> BaseModel:
        """
        Extract job information from file(s) or string.

        Args:
            file_path: Path to job description file (PDF, TXT, IMG) or list of paths
            job_text: Raw job description as string
            message: Extraction instruction
            output_schema: Schema for structured output
            system_prompt: Custom system prompt
        """
        if system_prompt is None:
            self.logger.info("No system prompt provided, using the default job extraction prompt.")
            system_prompt = """You are an expert recruiter assistant specializing in French job market.
            Extract and structure all job information comprehensively. Identify contract types:
            CDI (Contrat à Durée Indéterminée), CDD (Contrat à Durée Déterminée),
            Stage (Internship), Freelance, or Alternance (Work-study)."""

        if message is None:
            self.logger.info("No message provided, using the default job extraction message.")
            message = "Extract all job information in structured format"

        model = self.model.with_structured_output(output_schema) if output_schema else self.model
        self.logger.info("Starting job extraction")
        self.logger.debug(
            "extract_job called with file_path=%s job_text_present=%s output_schema=%s",
            file_path,
            bool(job_text),
            getattr(output_schema, "__name__", str(output_schema)),
        )

        if job_text:
            message_obj = self._build_text_message(message, job_text)
        elif file_path:
            file_paths = self._normalize_file_paths(file_path)
            self.logger.debug(
                "Job extraction using file input count=%s provider=%s",
                len(file_paths),
                self.config.provider,
            )
            message_obj = self._build_file_message(file_paths, message)
        else:
            raise ValueError("Provide either 'file_path' or 'job_text'")

        response = model.invoke(
            [
                SystemMessage(content=system_prompt),
                message_obj,
            ]
        )
        self.logger.info("Job extraction completed")
        self.logger.debug("Job extraction response type=%s", type(response).__name__)
        return response

    def analyze_job(
        self,
        job_information: JobPosition,
        output_schema: BaseModel,
        message: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """
        Analyze job posting for insights and requirements.
        """
        self.logger.info("Starting job analysis")
        self.logger.debug(
            "analyze_job called with job_title=%s company=%s output_schema=%s",
            job_information.job_title,
            job_information.company,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            self.logger.info("No system prompt provided, using the default job analysis prompt.")
            system_prompt = """You are an expert recruiter specializing in French job market.
            Analyze job postings to provide strategic insights about role requirements,
            difficulty level, market competitiveness, and candidate profile recommendations."""

        if message is None:
            self.logger.info("No message provided, using the default job analysis message.")
            message = "Analyze this job posting and provide recruiter insights"

        model = self.model.with_structured_output(output_schema)

        job_json = job_information.model_dump_json(indent=2)

        full_prompt = f"""
USER REQUEST:
{message}

JOB INFORMATION:
{job_json}
"""
        response = model.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=full_prompt),
            ]
        )
        self.logger.info("Job analysis completed")
        self.logger.debug("Job analysis response type=%s", type(response).__name__)
        return response

    def analyze_job_for_candidate(
        self,
        job_information: JobPosition,
        output_schema: BaseModel,
        message: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """
        Analyze job posting from candidate perspective.
        Focuses on career growth, compensation, work-life balance, and role fit.
        """
        self.logger.info("Starting candidate-perspective job analysis")
        self.logger.debug(
            "analyze_job_for_candidate called with job_title=%s company=%s output_schema=%s",
            job_information.job_title,
            job_information.company,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            self.logger.info("No system prompt provided, using the default candidate-perspective prompt.")
            system_prompt = """You are an expert career coach specializing in the French job market.
            Analyze job postings from a candidate perspective to help job seekers understand:
            - Career growth and learning opportunities
            - Work-life balance indicators
            - Compensation and benefits analysis
            - Whether this role would be a good fit for their career
            - Pros and cons of the position
            Focus on what matters to candidates, not recruiters."""

        if message is None:
            self.logger.info("No message provided, using the default candidate-perspective message.")
            message = "Analyze this job posting from a candidate's perspective"

        model = self.model.with_structured_output(output_schema)

        job_json = job_information.model_dump_json(indent=2)

        full_prompt = f"""
USER REQUEST:
{message}

JOB INFORMATION:
{job_json}
"""
        response = model.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=full_prompt),
            ]
        )
        self.logger.info("Candidate-perspective job analysis completed")
        self.logger.debug("Candidate-perspective analysis response type=%s", type(response).__name__)
        return response

    def analyze_job_for_recruiter(
        self,
        job_information: JobPosition,
        output_schema: BaseModel,
        message: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """
        Analyze job posting from recruiter perspective.
        Focuses on market position, hiring difficulty, candidate profile, and strategic insights.
        """
        self.logger.info("Starting recruiter-perspective job analysis")
        self.logger.debug(
            "analyze_job_for_recruiter called with job_title=%s company=%s output_schema=%s",
            job_information.job_title,
            job_information.company,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            self.logger.info("No system prompt provided, using the default recruiter-perspective prompt.")
            system_prompt = """You are an expert recruiter specializing in the French job market.
            Analyze job postings to provide strategic insights about:
            - Role complexity and seniority level
            - Critical skills and their market value
            - Market competitiveness and hiring difficulty
            - Ideal candidate profiles and requirements
            - Time to fill estimates and hiring risks
            Focus on what matters to recruiters and hiring managers."""

        if message is None:
            self.logger.info("No message provided, using the default recruiter-perspective message.")
            message = "Analyze this job posting from a recruiter's perspective"

        model = self.model.with_structured_output(output_schema)

        job_json = job_information.model_dump_json(indent=2)

        full_prompt = f"""
USER REQUEST:
{message}

JOB INFORMATION:
{job_json}
"""
        response = model.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=full_prompt),
            ]
        )
        self.logger.info("Recruiter-perspective job analysis completed")
        self.logger.debug("Recruiter-perspective analysis response type=%s", type(response).__name__)
        return response
