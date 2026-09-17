from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

from utils.logger import get_logger
from agents.agent_config import AgentConfig
from motivation_letter.agent import MotivationLetterAgent
from motivation_letter.service import MotivationLetterService
from motivation_letter.schema import (
    MotivationLetterRequest,
    MotivationLetter
)

logger = get_logger(name="motivation_letter.route", log_file="motivation_letter_api.log", level="INFO")

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent / "config/agent_config.yaml"
agent = None
service = MotivationLetterService()


from cv.schema import CVInformation
from jobs.schema import JobPosition

class FinalizeRequest(BaseModel):
    pdf_id: str
    company: str
    job_title: str


class CompileVerbatimRequest(BaseModel):
    cv_info: CVInformation
    job_info: JobPosition
    content: str


def _get_agent() -> MotivationLetterAgent:
    global agent
    if agent is not None:
        return agent
    return MotivationLetterAgent(config=AgentConfig(config_path=CONFIG_PATH))


@router.post("/generate", response_model=MotivationLetter)
async def generate_motivation_letter(request: MotivationLetterRequest) -> MotivationLetter:
    """
    Generate a motivation letter based on CV and job information
    """
    try:
        logger.info(
            "Received motivation letter request candidate=%s company=%s job_type=%s language=%s format=%s",
            request.cv_info.personal_info.name,
            request.job_info.company,
            request.job_type,
            request.language,
            request.return_format,
        )

        from starlette.concurrency import run_in_threadpool
        letter = await run_in_threadpool(_get_agent().generate_letter, request)
        letter = service.persist(request, letter)
        logger.info("Motivation letter generation completed successfully")
        return letter
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating motivation letter: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate motivation letter")


@router.post("/generate-temp-pdf")
async def generate_temp_pdf_endpoint(request: MotivationLetterRequest) -> dict:
    """Generate motivation letter draft and compile to a temporary PDF inside /tmp."""
    import uuid
    from starlette.concurrency import run_in_threadpool
    try:
        logger.info("Generating temporary PDF motivation letter draft")
        # 1. Generate letter text using agent
        letter = await run_in_threadpool(_get_agent().generate_letter, request)
        
        # 2. Compile to temporary PDF
        pdf_id = str(uuid.uuid4())
        pdf_path = service.generate_temp_pdf(request, letter.content, pdf_id)
        
        return {
            "pdf_id": pdf_id,
            "pdf_url": f"/api/motivation-letter/temp/{pdf_id}/file",
            "content": letter.content
        }
    except Exception as e:
        logger.error(f"Error generating temporary PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compile PDF draft: {str(e)}")


@router.get("/temp/{pdf_id}/file")
async def get_temp_pdf_file(pdf_id: str):
    """Retrieve temporary compiled PDF file."""
    pdf_path = service.db_base_dir / "motivation_letter" / "tmp" / pdf_id / "motivation_letter.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Temporary PDF not found or expired.")
    return FileResponse(pdf_path, media_type="application/pdf", content_disposition_type="inline")


@router.post("/compile-verbatim")
async def compile_verbatim_endpoint(request: CompileVerbatimRequest) -> dict:
    """Compile provided cover letter text verbatim to a temporary typeset PDF inside /tmp."""
    import uuid
    try:
        logger.info("Compiling user's manual edited text verbatim to typeset PDF")
        pdf_id = str(uuid.uuid4())
        
        # We need a MotivationLetterRequest structure for generate_temp_pdf
        from motivation_letter.schema import MotivationLetterRequest
        dummy_req = MotivationLetterRequest(
            cv_info=request.cv_info,
            job_info=request.job_info,
            job_type="corporation", # dummy value
        )
        
        pdf_path = service.generate_temp_pdf(dummy_req, request.content, pdf_id)
        return {
            "pdf_id": pdf_id,
            "pdf_url": f"/api/motivation-letter/temp/{pdf_id}/file",
            "content": request.content
        }
    except Exception as e:
        logger.error(f"Error compiling verbatim PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compile verbatim PDF: {str(e)}")


@router.post("/finalize")
async def finalize_temp_pdf_endpoint(req: FinalizeRequest) -> dict:
    """Move temporary PDF files to permanent results folder."""
    try:
        logger.info("Finalizing temporary PDF draft for company: %s", req.company)
        final_pdf_path, final_pdf_str = service.finalize_temp_pdf(req.pdf_id, req.company, req.job_title)
        return {
            "pdf_path": final_pdf_str
        }
    except Exception as e:
        logger.error(f"Error finalizing temporary PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save PDF permanently: {str(e)}")


@router.get("/formats")
async def get_supported_formats():
    """Get supported job types, languages, tones, and formats"""
    logger.info("Fetching supported formats")
    
    formats = {
        "job_types": ["startup", "phd", "corporation"],
        "languages": ["en", "fr"],
        "tones": ["professional", "academic", "formal"],
        "return_formats": ["txt", "latex"]
    }
    
    logger.info("Supported formats retrieved")
    return formats
