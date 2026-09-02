from fastapi import APIRouter, HTTPException
from pathlib import Path

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


def _get_agent() -> MotivationLetterAgent:
    global agent
    if agent is not None:
        return agent
    return MotivationLetterAgent(config=AgentConfig(config_path=CONFIG_PATH))


@router.post("/generate", response_model=MotivationLetter)
async def generate_motivation_letter(request: MotivationLetterRequest) -> MotivationLetter:
    """
    Generate a motivation letter based on CV and job information
    
    Args:
        request: MotivationLetterRequest containing:
            - cv_info: Candidate CV information
            - job_info: Target job position
            - job_type: "startup", "phd", or "corporation"
            - language: "en" or "fr"
            - tone: "professional", "academic", or "formal"
            - return_format: "txt" or "latex"
            - candidate_analysis: (optional) Pre-computed fit analysis
            - custom_context: (optional) User-provided additional context
    
    Returns:
        MotivationLetter with content and metadata
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