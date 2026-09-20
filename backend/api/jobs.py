from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form, Depends
from typing import Optional
from dotenv import load_dotenv

from utils.logger import get_logger
from infrastructure.jobs.analysis.agent import JobExtractionAgent
from infrastructure.agents.agent_config import AgentConfig
from application.jobs.analysis.service import JobService
from core.auth import TenantContext, get_tenant_context

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
    job_text: Optional[str] = Form(None, description="Raw job description text"),
    tenant: TenantContext = Depends(get_tenant_context),
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
        response = await _get_service().extract_job_from_input(file, file_path, job_text, tenant_id=tenant.tenant_id)
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
    job_data: Optional[str] = Form(None, description="JobPosition as JSON string"),
    tenant: TenantContext = Depends(get_tenant_context),
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
        response = await _get_service().analyze_job_candidate(file, file_path, job_text, job_data, tenant_id=tenant.tenant_id)
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
    job_data: Optional[str] = Form(None, description="JobPosition as JSON string"),
    tenant: TenantContext = Depends(get_tenant_context),
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
        response = await _get_service().analyze_job_recruiter(file, file_path, job_text, job_data, tenant_id=tenant.tenant_id)
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
    job_data: Optional[str] = Form(None, description="JobPosition as JSON string"),
    tenant: TenantContext = Depends(get_tenant_context),
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
        response = await _get_service().analyze_job(file, file_path, job_text, job_data, tenant_id=tenant.tenant_id)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ==========================================
# EXTENSIBLE JOB SEARCH PLATFORM API
# ==========================================
from pydantic import BaseModel
from domain.jobs.search.schema import UnifiedJobSearchResponse

class JobSearchRequest(BaseModel):
    provider: str = "france_travail"
    query: Optional[str] = None
    department: Optional[str] = None
    contract_type: Optional[str] = None
    page: int = 1
    limit: int = 25


class JobSearchChatRequest(BaseModel):
    message: str


@router.get("/providers")
async def list_providers():
    """Get list of active job search providers."""
    from infrastructure.jobs.search.providers.manager import JobProviderManager
    manager = JobProviderManager()
    return {"providers": manager.list_providers()}


@router.post("/search", response_model=UnifiedJobSearchResponse)
async def search_jobs(
    request: JobSearchRequest,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Programmatically search job listings across registered providers."""
    from infrastructure.jobs.search.providers.manager import JobProviderManager
    from starlette.concurrency import run_in_threadpool
    manager = JobProviderManager()
    try:
        results = await run_in_threadpool(
            manager.search_jobs,
            provider_name=request.provider,
            query=request.query,
            department=request.department,
            contract_type=request.contract_type,
            page=request.page,
            limit=request.limit,
        )
        return results
    except Exception as e:
        logger.error(f"Provider search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/search/{provider}/{job_id}")
async def get_job_detail(
    provider: str,
    job_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Retrieve detailed job posting info from a provider, mapped to JobPosition schema."""
    from infrastructure.jobs.search.providers.manager import JobProviderManager
    from starlette.concurrency import run_in_threadpool
    manager = JobProviderManager()
    try:
        details = await run_in_threadpool(
            manager.get_job_detail,
            provider_name=provider,
            job_id=job_id,
        )
        return details
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch job detail: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fetch failed: {str(e)}")


@router.post("/search/chat")
async def search_chat(
    request: JobSearchChatRequest,
    tenant: TenantContext = Depends(get_tenant_context),
):
    """AI-driven interactive job search chat using tool-calling."""
    from infrastructure.jobs.search.agent import JobSearchAgent
    from infrastructure.agents.agent_config import AgentConfig
    from starlette.concurrency import run_in_threadpool
    
    # Instantiate agent in request-execution scope to guarantee absolute statelessness
    # and prevent cross-tenant credential leakage (GEMINI.md section 3.3)
    search_agent = JobSearchAgent(config=AgentConfig(config_path=CONFIG_PATH))
    try:
        response_text = await run_in_threadpool(
            search_agent.run_chat_loop,
            user_message=request.message,
        )
        return {
            "response": response_text,
            "history": search_agent.get_history_dict()
        }
    except Exception as e:
        logger.error(f"Search chat agent failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat agent failed: {str(e)}")
