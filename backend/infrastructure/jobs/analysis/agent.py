import base64
import time
from pathlib import Path
from typing import Optional, Sequence, Union

from infrastructure.agents.base_agents import BaseAgent
from infrastructure.agents.agent_config import AgentConfig
from google import genai
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from domain.jobs.analysis.schema import JobPosition
from infrastructure.jobs.analysis.prompt import (
    SYSTEM_PROMPT_JOB_EXTRACTION,
    SYSTEM_PROMPT_JOB_ANALYSIS,
    SYSTEM_PROMPT_JOB_CANDIDATE,
    SYSTEM_PROMPT_JOB_RECRUITER,
)


class JobExtractionAgent(BaseAgent):

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        logger_name: str = "jobs.agent",
        log_file: str = "jobs_api.log",
        log_level: str = "INFO",
    ):
        super().__init__(
            config,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level,
        )
        self.logger.info(
            "JobExtractionAgent initialized with provider=%s api_key_set=%s",
            self.config.provider,
            self.config.is_api_key_set,
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
        self.logger.info("Detected mime_type=%s for file_path=%s", mime_type, file_path)
        return mime_type

    def _normalize_file_paths(
        self,
        file_path: Union[str, Path, Sequence[Union[str, Path]]],
    ) -> list[Path]:
        if isinstance(file_path, (str, Path)):
            return [Path(file_path)]
        return [Path(path) for path in file_path]

    def _build_text_message(self, message: str, job_text: str) -> HumanMessage:
        self.logger.info("Job extraction using raw text input")
        return HumanMessage(
            content=[
                {"type": "text", "text": message},
                {"type": "text", "text": f"Job Description:\n{job_text}"},
            ]
        )

    def _wait_for_uploaded_file(self, file):
        while file.state.name == "PROCESSING":
            self.logger.info("Job file still processing: %s", file.name)
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

        self.logger.info("Job extraction using Gemini file upload mode")
        content = [{"type": "text", "text": message}]

        for fpath in file_paths:
            self.logger.info("Uploading job file: %s", fpath)
            file = self.client.files.upload(file=str(fpath))
            file = self._wait_for_uploaded_file(file)

            mime_type = self._get_mime_type(fpath)
            self.logger.info("Job file ready uri=%s mime_type=%s", file.uri, mime_type)
            content.append(
                {
                    "type": "file",
                    "file_id": file.uri,
                    "mime_type": mime_type,
                }
            )

        self.logger.info("Job extraction message assembled with %s file blocks", len(content) - 1)
        return HumanMessage(content=content)

    def _build_vertex_file_message(
        self,
        file_paths: Sequence[Path],
        message: str,
    ) -> HumanMessage:
        self.logger.info("Job extraction using Vertex base64 mode")
        content = [{"type": "text", "text": message}]

        for fpath in file_paths:
            mime_type = self._get_mime_type(fpath)
            file_data = base64.b64encode(fpath.read_bytes()).decode("utf-8")
            self.logger.info(
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

        self.logger.info("Job extraction message assembled with %s file blocks", len(content) - 1)
        return HumanMessage(content=content)

    def _build_file_message(
        self,
        file_paths: Sequence[Path],
        message: str,
    ) -> HumanMessage:
        if self.config.provider == "api_key":
            return self._build_gemini_file_message(file_paths, message)
        return self._build_vertex_file_message(file_paths, message)

    def _extract_text_from_file(self, file_path: Union[str, Path]) -> str:
        file_path = Path(file_path)
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            try:
                import pdfplumber
                self.logger.info("Extracting text from PDF locally: %s", file_path)
                with pdfplumber.open(file_path) as pdf:
                    text_content = []
                    for i, page in enumerate(pdf.pages):
                        page_text = page.extract_text()
                        if page_text:
                            text_content.append(page_text)
                        else:
                            self.logger.warning("No text extracted from page %d of %s", i + 1, file_path)
                    full_text = "\n\n".join(text_content)
                    if not full_text or not full_text.strip():
                        raise RuntimeError(
                            f"The PDF file '{file_path.name}' is empty or scanned (contains images only). "
                            "Text-only LLM providers like Qwen require digital PDFs with selectable text. "
                            "Please upload a digital PDF, or use a multimodal provider like Gemini."
                        )
                    self.logger.info("Successfully extracted %d characters from PDF: %s", len(full_text), file_path)
                    return full_text
            except Exception as e:
                self.logger.error("Failed to extract text from PDF %s: %s", file_path, str(e), exc_info=True)
                raise RuntimeError(f"Failed to parse PDF file: {str(e)}")
        elif ext == ".txt":
            try:
                self.logger.info("Reading text from TXT file locally: %s", file_path)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception as e:
                self.logger.error("Failed to read TXT file %s: %s", file_path, str(e), exc_info=True)
                raise RuntimeError(f"Failed to read TXT file: {str(e)}")
        else:
            self.logger.warning("Unsupported file format for local text extraction: %s", ext)
            raise ValueError(f"File type {ext} is not supported for text extraction on provider '{self.config.provider}'")

    def extract_job_to_job_position(
        self,
        full_description: str,
        output_schema: BaseModel = JobPosition,
        system_prompt: Optional[str] = None,
        message: Optional[str] = None
    ) -> JobPosition:
        """
        Uses LLM to extract job information from a full job description text
        directly into the JobPosition schema.
        """
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT_JOB_EXTRACTION
        if message is None:
            message = "Extract all job information in structured format from the provided Job Description. Ensure the output strictly adheres to the JobPosition schema."

        model = self.model.with_structured_output(output_schema)

        self.logger.info("Calling LLM for structured job extraction.")
        response = model.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Job Description:\n{full_description}"),
            ]
        )
        self.logger.info("LLM job extraction completed. Response type=%s", type(response).__name__)
        return response

    def extract_job(
        self,
        job_text: str,
        output_schema: Optional[BaseModel] = None,
        system_prompt: Optional[str] = None,
        message: Optional[str] = None
    ) -> JobPosition:
        """
        Extract job information from raw text using the LLM directly into the JobPosition schema.

        Args:
            job_text: Raw job description as string.
            output_schema: Schema for structured output (defaults to JobPosition).
            system_prompt: Custom system prompt.
            message: Extraction instruction.
        """
        if not job_text:
            raise ValueError("'job_text' must be provided for LLM extraction.")

        if output_schema is None:
            output_schema = JobPosition

        if system_prompt is None:
            self.logger.info("No system prompt provided for extraction, using default.")
            system_prompt = SYSTEM_PROMPT_JOB_EXTRACTION

        if message is None:
            self.logger.info("No message provided for extraction, using default.")
            message = "Extract all job information in structured format from the provided Job Description. Ensure the output strictly adheres to the JobPosition schema."

        model = self.model.with_structured_output(output_schema)

        self.logger.info("Calling LLM for structured job extraction with output_schema=%s", getattr(output_schema, "__name__", str(output_schema)))
        response = model.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"{message}\n\nJOB DESCRIPTION:\n{job_text}"),
            ]
        )
        self.logger.info("LLM job extraction completed. Response type=%s", type(response).__name__)
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
        self.logger.info(
            "analyze_job called with job_title=%s company=%s output_schema=%s",
            job_information.job_title,
            job_information.company,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            self.logger.info("No system prompt provided, using the default job analysis prompt.")
            system_prompt = SYSTEM_PROMPT_JOB_ANALYSIS

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
        self.logger.info("Job analysis response type=%s", type(response).__name__)
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
        self.logger.info(
            "analyze_job_for_candidate called with job_title=%s company=%s output_schema=%s",
            job_information.job_title,
            job_information.company,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            self.logger.info("No system prompt provided, using the default candidate-perspective prompt.")
            system_prompt = SYSTEM_PROMPT_JOB_CANDIDATE

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
        self.logger.info("Candidate-perspective analysis completed and response type=%s", type(response).__name__)
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
        # self.logger.info("Starting recruiter-perspective job analysis")
        self.logger.info(
            "analyze_job_for_recruiter called with job_title=%s company=%s output_schema=%s",
            job_information.job_title,
            job_information.company,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            self.logger.info("No system prompt provided, using the default recruiter-perspective prompt.")
            system_prompt = SYSTEM_PROMPT_JOB_RECRUITER

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
        self.logger.info("Recruiter-perspective analysis completed and response type=%s", type(response).__name__)
        return response
