import base64
import time
from pathlib import Path
from typing import Dict, Optional, Union

from agents import BaseAgent, AgentConfig
from cv.schema import CVInformation
from cv.prompt import SYSTEM_PROMPT_EXTRACTION, SYSTEM_PROMPT_ANALYSIS

from pydantic import BaseModel

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from google import genai

class CVAnalysisAgent(BaseAgent):
    
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        logger_name: str = "cv.agent",
        log_file: str = "cv_api.log",
        log_level: str = "INFO",
    ):
        super().__init__(
            config,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level,
        )
        self.logger.info(
            "CVAnalysisAgent initialized with provider=%s api_key_set=%s",
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
        self.logger.info("Detected mime_type=%s for file_path=%s", mime_type, file_path)
        return mime_type

    def _wait_for_uploaded_file(self, file):
        while file.state.name == "PROCESSING":
            self.logger.info("CV file still processing: %s", file.name)
            time.sleep(2)
            file = self.client.files.get(name=file.name)
        return file

    def _build_gemini_file_message(self, file_path: Union[str, Path], message: str) -> HumanMessage:
        if not self.client:
            raise RuntimeError("Gemini API client is not initialized for api_key mode")

        self.logger.info("CV extraction using Gemini file upload mode")
        file = self.client.files.upload(file=str(file_path))
        self.logger.info("Uploaded CV file uri=%s", getattr(file, "uri", None))
        file = self._wait_for_uploaded_file(file)
        self.logger.info("CV file processing complete: %s", file.name)

        return HumanMessage(
            content=[
                {"type": "text", "text": message},
                {"type": "file", "file_id": file.uri, "mime_type": self._get_mime_type(file_path)},
            ]
        )

    def _build_vertex_file_message(self, file_path: Union[str, Path], message: str) -> HumanMessage:
        self.logger.info("CV extraction using Vertex base64 mode")
        file_data = base64.b64encode(Path(file_path).read_bytes()).decode("utf-8")

        return HumanMessage(
            content=[
                {"type": "text", "text": message},
                {
                    "type": "file",
                    "source_type": "base64",
                    "mime_type": self._get_mime_type(file_path),
                    "data": file_data,
                },
            ]
        )
        
    def extract_cv(
        self, 
        file_path: Union[str, Path], 
        message: str,
        output_schema: Optional[BaseModel] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Union[BaseMessage, Dict]:
        """
        Extract information from CV
        """
        self.logger.info("Starting CV extraction")
        self.logger.info(
            "extract_cv called with file_path=%s output_schema=%s",
            file_path,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT_EXTRACTION or "You are a virtual assistant designed to extract information from CVs"
            self.logger.info("No system prompt provided, using the CV prompt file default")
        
        model = self.model.with_structured_output(output_schema) if output_schema else self.model
        self.logger.info("Using structured output=%s", bool(output_schema))
        
        if self.config.provider == "api_key":
            message_obj = self._build_gemini_file_message(file_path, message)
        else:
            message_obj = self._build_vertex_file_message(file_path, message)
        
        response = model.invoke([
            SystemMessage(content=system_prompt),
            message_obj
        ])
        self.logger.info("CV extraction completed")
        self.logger.info("CV extraction response type=%s", type(response).__name__)
        return response

    def analyze_cv(
        self,
        cv_information: CVInformation,
        output_schema: BaseModel, 
        message: str,
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """
        Analyze candidate information.
        """
        self.logger.info("Starting CV analysis")
        self.logger.info(
            "analyze_cv called with candidate=%s output_schema=%s",
            cv_information.personal_info.name,
            getattr(output_schema, "__name__", str(output_schema)),
        )
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT_ANALYSIS or "You are a virtual assistant designed to analyze CV information."
            self.logger.info("No system prompt provided, using the CV prompt file default")
        
        model = self.model.with_structured_output(output_schema)
        self.logger.info("Using structured output for CV analysis")
        
        cv_json = cv_information.model_dump_json(indent=2)
        self.logger.info("Built CV JSON payload length=%s", len(cv_json))
        
        full_prompt = f"""
USER REQUEST: 
{message}

CV INFORMATION:
{cv_json}        
"""
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=full_prompt)
        ])
        self.logger.info("CV analysis completed")
        self.logger.info("CV analysis response type=%s", type(response).__name__)
        return response