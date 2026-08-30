from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from typing import Optional
from dotenv import load_dotenv

from utils.logger import get_logger
from jobs.agent import JobExtractionAgent
from agents.agent_config import AgentConfig
from jobs.service import JobService

logger = get_logger(name="jobs.route", log_file="jobs_api.log", level="INFO")
load_dotenv()

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent / "config/agent_config.yaml"
agent = None


def _get_service() -> JobService:
    global agent
    active_agent = agent
    if active_agent is None:
        active_agent = JobExtractionAgent(config=AgentConfig(config_path=CONFIG_PATH))
    return JobService(agent=active_agent)


# ==========================================
# API 1: EXTRACT JOB INFORMATION
# ==========================================
@router.post("/extract")
async def extract_job(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Query(None, description="Path to job description file"),
    job_text: Optional[str] = Form(None, description="Raw job description text")
):
    """Extract job information from French job description."""
    
    # logger.info("Starting job extraction")
    logger.info(
        "extract_job called with file_present=%s file_path_present=%s job_text_present=%s",
        bool(file),
        bool(file_path),
        bool(job_text),
    )
    
    try:
        response = await _get_service().extract_job_from_input(file, file_path, job_text)
        logger.info("Job extraction response prepared successfully")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job extraction failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

# ==========================================
# API 2a: ANALYZE JOB - CANDIDATE PERSPECTIVE
# ==========================================
@router.post("/analyze/candidate")
async def analyze_job_candidate(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Query(None, description="Path to job description file"),
    job_text: Optional[str] = Form(None, description="Raw job description text"),
    job_data: Optional[str] = Form(None, description="JobPosition as JSON string")
):
    """
    Analyze job posting from a candidate's perspective only.
    First extracts job information (if needed), then returns candidate-focused analysis.
    """
    
    # logger.info("Starting job analysis (candidate)")
    logger.info(
        "analyze_job_candidate called with file_present=%s file_path_present=%s job_text_present=%s job_data_present=%s",
        bool(file),
        bool(file_path),
        bool(job_text),
        bool(job_data),
    )
    
    try:
        response = await _get_service().analyze_job_candidate(file, file_path, job_text, job_data)
        logger.info("Candidate analysis successful")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Candidate analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ==========================================
# API 2b: ANALYZE JOB - RECRUITER PERSPECTIVE
# ==========================================
@router.post("/analyze/recruiter")
async def analyze_job_recruiter(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Query(None, description="Path to job description file"),
    job_text: Optional[str] = Form(None, description="Raw job description text"),
    job_data: Optional[str] = Form(None, description="JobPosition as JSON string")
):
    """
    Analyze job posting from a recruiter's perspective only.
    First extracts job information (if needed), then returns recruiter-focused analysis.
    """
    
    # logger.info("Starting job analysis (recruiter)")
    logger.info(
        "analyze_job_recruiter called with file_present=%s file_path_present=%s job_text_present=%s job_data_present=%s",
        bool(file),
        bool(file_path),
        bool(job_text),
        bool(job_data),
    )
    
    try:
        response = await _get_service().analyze_job_recruiter(file, file_path, job_text, job_data)
        logger.info("Recruiter analysis successful")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Recruiter analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ==========================================
# LEGACY API: ANALYZE JOB - BOTH PERSPECTIVES
# ==========================================
@router.post("/analyze")
async def analyze_job(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Query(None, description="Path to job description file"),
    job_text: Optional[str] = Form(None, description="Raw job description text"),
    job_data: Optional[str] = Form(None, description="JobPosition as JSON string")
):
    """
    Legacy compatibility endpoint that returns both candidate and recruiter analysis.
    """
    logger.info(
        "analyze_job called with file_present=%s file_path_present=%s job_text_present=%s job_data_present=%s",
        bool(file),
        bool(file_path),
        bool(job_text),
        bool(job_data),
    )

    try:
        response = await _get_service().analyze_job(file, file_path, job_text, job_data)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")