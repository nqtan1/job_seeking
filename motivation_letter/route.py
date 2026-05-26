from fastapi import APIRouter, HTTPException
from datetime import datetime
import json
from pathlib import Path
import unicodedata
import re

from utils.logger import get_logger
from motivation_letter.agent import MotivationLetterAgent
from motivation_letter.schema import (
    MotivationLetterRequest,
    MotivationLetter
)

logger = get_logger(name="motivation_letter.route", log_file="motivation_letter_api.log", level="DEBUG")

router = APIRouter()
agent = MotivationLetterAgent()

# Base folder structure
RESULT_BASE_DIR = Path(__file__).parent.parent / "db/motivation_letter/generate"
RESULT_BASE_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(text: str) -> str:
    """Sanitize text for use in folder names"""
    # Normalize unicode characters
    text = unicodedata.normalize('NFKD', text)
    # Remove non-ASCII characters
    text = text.encode('ASCII', 'ignore').decode('ASCII')
    # Replace spaces with underscores
    text = text.replace(" ", "_")
    # Remove special characters, keep only alphanumeric and underscore
    text = re.sub(r'[^a-zA-Z0-9_-]', '', text)
    return text


def _get_result_folder(company: str, job_title: str) -> Path:
    """
    Create and return result folder with timestamp and job info structure:
    db/motivation_letter/generate/YYYY-MM-DD_HHmmss_Company_JobTitle/
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    
    # Sanitize company and job title
    safe_company = _sanitize_filename(company)[:50]  # Limit length
    safe_job_title = _sanitize_filename(job_title)[:50]
    
    folder_name = f"{timestamp}_{safe_company}_{safe_job_title}"
    result_dir = RESULT_BASE_DIR / folder_name
    result_dir.mkdir(parents=True, exist_ok=True)
    
    logger.debug(f"Result folder created: {result_dir}")
    return result_dir


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
            f"Received motivation letter request - "
            f"candidate: {request.cv_info.personal_info.name}, "
            f"company: {request.job_info.company}, "
            f"job_type: {request.job_type}, "
            f"language: {request.language}, "
            f"format: {request.return_format}"
        )
        
        # Generate letter
        logger.debug("Calling agent to generate letter")
        letter = agent.generate_letter(request)
        
        # Create result folder
        logger.debug("Creating result folder structure")
        result_folder = _get_result_folder(
            company=request.job_info.company,
            job_title=request.job_info.job_title
        )
        
        # Save generated letter
        logger.debug(f"Saving letter content")
        letter_file = result_folder / f"motivation_letter.{request.return_format}"
        
        with open(letter_file, "w", encoding="utf-8") as f:
            f.write(letter.content)
        
        logger.info(f"Letter content saved to: {letter_file}")
        
        # Save metadata
        logger.debug("Saving metadata")
        metadata_file = result_folder / "metadata.json"
        metadata_dict = letter.metadata.model_dump()
        metadata_dict["generated_at"] = metadata_dict["generated_at"].isoformat()
        metadata_dict["candidate_name"] = request.cv_info.personal_info.name
        metadata_dict["candidate_email"] = request.cv_info.personal_info.email
        metadata_dict["company"] = request.job_info.company
        metadata_dict["job_title"] = request.job_info.job_title
        
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Metadata saved to: {metadata_file}")
        
        # Save request details (for reference)
        logger.debug("Saving request details")
        request_file = result_folder / "request.json"
        request_dict = request.model_dump()
        request_dict["cv_info"]["personal_info"]["email"] = str(request_dict["cv_info"]["personal_info"]["email"])  # Convert EmailStr to str
        
        with open(request_file, "w", encoding="utf-8") as f:
            json.dump(request_dict, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"Request details saved to: {request_file}")
        
        logger.info(
            f"Motivation letter generation completed successfully - "
            f"saved to {result_folder}"
        )
        
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
    logger.debug("Fetching supported formats")
    
    formats = {
        "job_types": ["startup", "phd", "corporation"],
        "languages": ["en", "fr"],
        "tones": ["professional", "academic", "formal"],
        "return_formats": ["txt", "latex"]
    }
    
    logger.info("Supported formats retrieved")
    return formats