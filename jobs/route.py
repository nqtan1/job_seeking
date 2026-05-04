import json
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from typing import Optional, List
from dotenv import load_dotenv
from datetime import datetime
import unicodedata
import re

from utils.logger import get_logger
from jobs.agent import JobExtractionAgent
from jobs.schema import JobPosition, CandidateAnalysis, RecruiterAnalysis

logger = get_logger(name="jobs.route", log_file="jobs_api.log", level="DEBUG")
load_dotenv()

router = APIRouter()
agent = JobExtractionAgent()

# Allowed file extensions (PDF, TXT, IMG)
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".jpg", ".jpeg", ".png", ".img"}
MAX_FILE_SIZE = 10 * 1024 * 1024
UPLOAD_BASE_DIR = Path(__file__).parent.parent / "db/jobs/uploads"
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Helper function to get upload folder with date structure
def _get_upload_folder() -> Path:
    """
    Get or create upload folder with date structure:
    db/jobs/uploads/YYYY-MM-DD/
    """
    date_folder = datetime.now().strftime("%Y-%m-%d")
    upload_dir = UPLOAD_BASE_DIR / date_folder
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir

# Helper function to create result folders with timestamp
def _get_result_folders(company: str, job_title: str) -> tuple[Path, Path]:
    """
    Create and return both extraction and analysis result folders with structure:
    db/jobs/extract/YYYY-MM-DD_HHMMSS_Company_JobTitle/
    db/jobs/analyze/YYYY-MM-DD_HHMMSS_Company_JobTitle/
    
    Returns: (extraction_dir, analysis_dir)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder_name = f"{timestamp}_{company}_{job_title}".replace(" ", "_").replace("/", "_")
    
    extraction_dir = Path(__file__).parent.parent / "db/jobs/extract" / folder_name
    analysis_dir = Path(__file__).parent.parent / "db/jobs/analyze" / folder_name
    
    extraction_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    
    return extraction_dir, analysis_dir

# ==========================================
# Helper function: Sanitize filename
# ==========================================
def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing/replacing special characters.
    Handles Unicode characters like accents (é, ê, ô, etc.)
    """
    # Normalize Unicode characters (decompose accents)
    filename = unicodedata.normalize('NFKD', filename)
    # Remove non-ASCII characters
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    # Replace spaces and special chars with underscores
    filename = re.sub(r'[^\w\s.-]', '_', filename)
    # Replace multiple spaces/underscores with single underscore
    filename = re.sub(r'[\s_]+', '_', filename)
    # Remove trailing underscores
    filename = filename.rstrip('_')
    return filename

# ==========================================
# Helper function: Validate and get file path
# ==========================================
async def _validate_and_get_file_path(
    file: Optional[UploadFile],
    file_path: Optional[str],
    operation: str = "operation"
) -> tuple[str, str]:
    """
    Validate file and return (file_path, filename).
    Supports PDF, TXT, JPG, PNG, IMG
    """
    if file and file_path:
        logger.warning(f"{operation}: Both file and file_path provided, using file upload")
    
    if file:
        logger.info(f"{operation}: Processing uploaded file: {file.filename}")
        
        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            logger.warning(f"Invalid file extension: {file_extension}")
            raise HTTPException(status_code=400, detail="File type not allowed (PDF, TXT, JPG, PNG, IMG)")
        
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            logger.warning(f"File size exceeded: {len(file_content)} bytes")
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit"
            )
        
        await file.seek(0)
        
        # Sanitize filename for API compatibility
        sanitized_filename = _sanitize_filename(file.filename)
        upload_dir = _get_upload_folder()
        saved_path = upload_dir / sanitized_filename
        with open(saved_path, "wb") as f:
            f.write(file_content)
        
        logger.debug(f"File saved: {saved_path} (original: {file.filename})")
        return str(saved_path), file.filename
    
    elif file_path:
        logger.info(f"{operation}: Using file path: {file_path}")
        
        if not Path(file_path).exists():
            logger.warning(f"File not found: {file_path}")
            raise HTTPException(status_code=404, detail="File not found")
        
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            logger.warning(f"Invalid file extension: {file_extension}")
            raise HTTPException(status_code=400, detail="File type not allowed (PDF, TXT, JPG, PNG, IMG)")
        
        file_size = Path(file_path).stat().st_size
        if file_size > MAX_FILE_SIZE:
            logger.warning(f"File size exceeded: {file_size} bytes")
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit"
            )
        
        return file_path, Path(file_path).name
    
    else:
        logger.warning(f"{operation}: Neither file nor file_path provided")
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file' (upload), 'file_path', or 'job_text' (raw text)"
        )

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
    
    logger.info("Starting job extraction")
    
    try:
        if job_text:
            logger.info("Extracting from raw text")
            extracted_data = agent.extract_job(
                job_text=job_text,
                message="Extract all information from this job description",
                output_schema=JobPosition
            )
            filename = "raw_text_input"
        
        elif file:
            logger.info("Processing uploaded file")
            processed_file_path, filename = await _validate_and_get_file_path(
                file, None, "Extract"
            )
            extracted_data = agent.extract_job(
                file_path=processed_file_path,
                message="Extract all information from this job description",
                output_schema=JobPosition
            )
        
        elif file_path:
            processed_file_path, filename = await _validate_and_get_file_path(
                None, file_path, "Extract"
            )
            extracted_data = agent.extract_job(
                file_path=processed_file_path,
                message="Extract all information from this job description",
                output_schema=JobPosition
            )
        
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide either 'file', 'file_path', or 'job_text'"
            )
        
        logger.info(f"Job extraction successful: {extracted_data.job_title} at {extracted_data.company}")
        
        # Save extracted data to folder structure
        extraction_dir, _ = _get_result_folders(extracted_data.company, extracted_data.job_title)
        extract_path = extraction_dir / "extraction.json"
        
        with open(extract_path, "w", encoding="utf-8") as f:
            f.write(extracted_data.model_dump_json(indent=2))
        
        logger.debug(f"Extracted data saved: {extract_path}")
        
        return {
            "message": "Job extraction successful",
            "job_title": extracted_data.job_title,
            "company": extracted_data.company,
            "data": extracted_data.model_dump(),
            "extract_path": str(extract_path),
            "result_folder": str(extraction_dir)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job extraction failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

# ==========================================
# API 2: ANALYZE JOB
# ==========================================
@router.post("/analyze")
async def analyze_job(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Query(None, description="Path to job description file"),
    job_text: Optional[str] = Form(None, description="Raw job description text"),
    job_data: Optional[str] = Form(None, description="JobPosition as JSON string")
):
    """
    Analyze job posting from both candidate and recruiter perspectives.
    First extracts job information, then provides dual analysis views.
    """
    
    logger.info("Starting job analysis")
    
    try:
        # ==========================================
        # Step 1: Get or extract job information
        # ==========================================
        if job_data and job_data.strip():
            try:
                if job_data.strip().startswith('{'):
                    logger.debug("Parsing JobPosition JSON data")
                    job_information = JobPosition(**json.loads(job_data))
                    logger.info(f"Using provided JobPosition: {job_information.job_title}")
                else:
                    job_text = job_data
                    job_data = None
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
        
        if not job_data or not job_data.strip():
            if job_text:
                logger.info("Extracting job information from raw text")
                job_information = agent.extract_job(
                    job_text=job_text,
                    message="Extract all information from this job description",
                    output_schema=JobPosition
                )
            elif file:
                logger.info("Extracting job information from uploaded file")
                processed_file_path, _ = await _validate_and_get_file_path(
                    file, None, "Analyze"
                )
                job_information = agent.extract_job(
                    file_path=processed_file_path,
                    message="Extract all information from this job description",
                    output_schema=JobPosition
                )
            elif file_path:
                logger.info("Extracting job information from file path")
                processed_file_path, _ = await _validate_and_get_file_path(
                    None, file_path, "Analyze"
                )
                job_information = agent.extract_job(
                    file_path=processed_file_path,
                    message="Extract all information from this job description",
                    output_schema=JobPosition
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Provide file, file_path, job_text, or job_data"
                )
        
        logger.info(f"Job extracted: {job_information.job_title} at {job_information.company}")
        
        # ==========================================
        # Step 2: Analyze from candidate perspective
        # ==========================================
        logger.debug("Analyzing job from candidate perspective")
        candidate_analysis = agent.analyze_job_for_candidate(
            job_information=job_information,
            output_schema=CandidateAnalysis,
            message="Analyze this job posting from a candidate's perspective"
        )
        logger.debug("Candidate analysis completed")
        
        # ==========================================
        # Step 3: Analyze from recruiter perspective
        # ==========================================
        logger.debug("Analyzing job from recruiter perspective")
        recruiter_analysis = agent.analyze_job_for_recruiter(
            job_information=job_information,
            output_schema=RecruiterAnalysis,
            message="Analyze this job posting from a recruiter's perspective"
        )
        logger.debug("Recruiter analysis completed")
        
        # ==========================================
        # Step 4: Prepare results
        # ==========================================
        logger.info(f"Job analysis successful: {job_information.job_title}")
        
        # ==========================================
        # Step 5: Save results
        # ==========================================
        extraction_dir, analysis_dir = _get_result_folders(job_information.company, job_information.job_title)
        
        # Save extraction
        extraction_path = extraction_dir / "extraction.json"
        with open(extraction_path, "w", encoding="utf-8") as f:
            f.write(job_information.model_dump_json(indent=2))
        logger.debug(f"Extraction saved: {extraction_path}")
        
        # Save candidate analysis
        candidate_analysis_path = analysis_dir / "candidate_analysis.json"
        with open(candidate_analysis_path, "w", encoding="utf-8") as f:
            f.write(candidate_analysis.model_dump_json(indent=2))
        logger.debug(f"Candidate analysis saved: {candidate_analysis_path}")
        
        # Save recruiter analysis
        recruiter_analysis_path = analysis_dir / "recruiter_analysis.json"
        with open(recruiter_analysis_path, "w", encoding="utf-8") as f:
            f.write(recruiter_analysis.model_dump_json(indent=2))
        logger.debug(f"Recruiter analysis saved: {recruiter_analysis_path}")
        
        return {
            "message": "Job analysis successful",
            "job_title": job_information.job_title,
            "company": job_information.company,
            "job_information": job_information.model_dump(),
            "candidate_analysis": candidate_analysis.model_dump(),
            "recruiter_analysis": recruiter_analysis.model_dump(),
            "extraction_folder": str(extraction_dir),
            "analysis_folder": str(analysis_dir),
            "extraction_path": str(extraction_path),
            "candidate_analysis_path": str(candidate_analysis_path),
            "recruiter_analysis_path": str(recruiter_analysis_path)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
