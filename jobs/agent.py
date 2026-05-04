from agents import BaseAgent, AgentConfig
from jobs.schema import JobPosition, JobAnalysis
from typing import Optional, Union
from pathlib import Path
import time
from pydantic import BaseModel
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from google import genai

class JobExtractionAgent(BaseAgent):
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self.client = genai.Client(api_key=self.config.api_key)
    
    def _get_mime_type(self, file_path: Union[str, Path]) -> str:
        """Determine MIME type based on file extension"""
        ext = Path(file_path).suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".img": "application/octet-stream"
        }
        return mime_types.get(ext, "application/octet-stream")
    
    def extract_job(
        self, 
        file_path: Optional[Union[str, Path, list]] = None,
        job_text: Optional[str] = None,
        message: Optional[str] = None,
        output_schema: Optional[BaseModel] = None,
        system_prompt: Optional[str] = None,
        **kwargs
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
            system_prompt = """You are an expert recruiter assistant specializing in French job market.
            Extract and structure all job information comprehensively. Identify contract types:
            CDI (Contrat à Durée Indéterminée), CDD (Contrat à Durée Déterminée), 
            Stage (Internship), Freelance, or Alternance (Work-study)."""
        
        if message is None:
            message = "Extract all job information in structured format"
        
        model = self.model.with_structured_output(output_schema) if output_schema else self.model
        
        # Handle string input
        if job_text:
            message_obj = HumanMessage(
                content=[
                    {"type": "text", "text": message},
                    {"type": "text", "text": f"Job Description:\n{job_text}"}
                ]
            )
        
        # Handle file input (single or multiple)
        else:
            content = [{"type": "text", "text": message}]
            
            # Convert single file_path to list for uniform processing
            file_paths = file_path if isinstance(file_path, list) else [file_path]
            
            for fpath in file_paths:
                file = self.client.files.upload(file=fpath)
                
                # Wait for file processing
                while file.state.name == "PROCESSING":
                    time.sleep(2)
                    file = self.client.files.get(name=file.name)
                
                mime_type = self._get_mime_type(fpath)
                
                content.append({
                    "type": "file",
                    "file_id": file.uri,
                    "mime_type": mime_type
                })
            
            message_obj = HumanMessage(content=content)
        
        response = model.invoke([
            SystemMessage(content=system_prompt),
            message_obj
        ])
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
        if system_prompt is None:
            system_prompt = """You are an expert recruiter specializing in French job market.
            Analyze job postings to provide strategic insights about role requirements, 
            difficulty level, market competitiveness, and candidate profile recommendations."""
        
        if message is None:
            message = "Analyze this job posting and provide recruiter insights"
        
        model = self.model.with_structured_output(output_schema)
        
        job_json = job_information.model_dump_json(indent=2)
        
        full_prompt = f"""
USER REQUEST:
{message}

JOB INFORMATION:
{job_json}
"""
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=full_prompt)
        ])
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
        if system_prompt is None:
            system_prompt = """You are an expert career coach specializing in the French job market.
            Analyze job postings from a candidate perspective to help job seekers understand:
            - Career growth and learning opportunities
            - Work-life balance indicators
            - Compensation and benefits analysis
            - Whether this role would be a good fit for their career
            - Pros and cons of the position
            Focus on what matters to candidates, not recruiters."""
        
        if message is None:
            message = "Analyze this job posting from a candidate's perspective"
        
        model = self.model.with_structured_output(output_schema)
        
        job_json = job_information.model_dump_json(indent=2)
        
        full_prompt = f"""
USER REQUEST:
{message}

JOB INFORMATION:
{job_json}
"""
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=full_prompt)
        ])
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
        if system_prompt is None:
            system_prompt = """You are an expert recruiter specializing in the French job market.
            Analyze job postings to provide strategic insights about:
            - Role complexity and seniority level
            - Critical skills and their market value
            - Market competitiveness and hiring difficulty
            - Ideal candidate profiles and requirements
            - Time to fill estimates and hiring risks
            Focus on what matters to recruiters and hiring managers."""
        
        if message is None:
            message = "Analyze this job posting from a recruiter's perspective"
        
        model = self.model.with_structured_output(output_schema)
        
        job_json = job_information.model_dump_json(indent=2)
        
        full_prompt = f"""
USER REQUEST:
{message}

JOB INFORMATION:
{job_json}
"""
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=full_prompt)
        ])
        return response
