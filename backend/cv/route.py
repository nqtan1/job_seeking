import json
import os
from pathlib import Path
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form, Depends
from fastapi.responses import FileResponse
from typing import Optional
from dotenv import load_dotenv
import unicodedata
import re

from utils.logger import get_logger 
from cv.agent import CVAnalysisAgent 
from cv.schema import CVInformation, BaseCandidateAnalysis
from agents.agent_config import AgentConfig
from core.auth import TenantContext, get_tenant_context
from workers.background import get_background_job_manager

logger = get_logger(name="cv.route", log_file="cv_api.log", level="INFO")
load_dotenv()

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent / "config/agent_config.yaml"
agent = None


def _get_agent() -> CVAnalysisAgent:
    global agent
    if agent is not None:
        return agent
    return CVAnalysisAgent(config=AgentConfig(config_path=CONFIG_PATH))

# Allowed file extensions 
ALLOWED_EXTENSIONS = {".pdf", ".img", ".txt", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 10 * 1024 * 1024

# Set up clean data directory path supporting GCS FUSE
data_dir_env = os.getenv("DATA_DIR")
if data_dir_env:
    DB_BASE_DIR = Path(data_dir_env)
else:
    DB_BASE_DIR = Path(__file__).parent.parent / "db"

UPLOAD_BASE_DIR = DB_BASE_DIR / "cv" / "uploads"
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Helper function to get upload folder with date structure
def _get_upload_folder() -> Path:
    """
    Get or create upload folder with date structure:
    db/cv/uploads/YYYY-MM-DD/
    """
    from datetime import datetime
    date_folder = datetime.now().strftime("%Y-%m-%d")
    upload_dir = UPLOAD_BASE_DIR / date_folder
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Using CV upload folder: %s", upload_dir)
    return upload_dir

# Helper function to create result folders with timestamp
def _get_result_folders() -> tuple[Path, Path]:
    """
    Create and return both extraction and analysis result folders with structure:
    db/cv/extract/YYYY-MM-DD_HHMMSS/
    db/cv/analyze/YYYY-MM-DD_HHMMSS/
    
    Returns: (extraction_dir, analysis_dir)
    """
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    
    extraction_dir = DB_BASE_DIR / "cv" / "extract" / timestamp
    analysis_dir = DB_BASE_DIR / "cv" / "analyze" / timestamp
    
    extraction_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Using CV result folders: extraction=%s analysis=%s", extraction_dir, analysis_dir)
    
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
    logger.info("Sanitized CV filename to: %s", filename)
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
    Validate file and return (file_path, filename)
    
    Args:
        file: Uploaded file object
        file_path: Path to existing file
        operation: Operation name for logging
    
    Returns:
        Tuple of (file_path, filename)
    """
    logger.info(
        "%s validation started with file_present=%s file_path_present=%s",
        operation,
        bool(file),
        bool(file_path),
    )
    if file and file_path:
        logger.warning(f"{operation}: Both file and file_path provided, using file upload")
    
    if file:
        # Process uploaded file
        logger.info(f"{operation}: Processing uploaded file: {file.filename}")
        
        file_extension = Path(file.filename).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            logger.warning(f"Invalid file extension: {file_extension}")
            raise HTTPException(status_code=400, detail="File type not allowed")
        
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
        
        logger.info(f"File saved: {saved_path} (original: {file.filename})")
        logger.info("%s validation completed using uploaded file", operation)
        return str(saved_path), file.filename
    
    elif file_path:
        # Use existing file path
        logger.info(f"{operation}: Using file path: {file_path}")
        
        if not Path(file_path).exists():
            logger.warning(f"File not found: {file_path}")
            raise HTTPException(status_code=404, detail="File not found")
        
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            logger.warning(f"Invalid file extension: {file_extension}")
            raise HTTPException(status_code=400, detail="File type not allowed")
        
        file_size = Path(file_path).stat().st_size
        if file_size > MAX_FILE_SIZE:
            logger.warning(f"File size exceeded: {file_size} bytes")
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds {MAX_FILE_SIZE // (1024 * 1024)} MB limit"
            )
        
        logger.info("%s validation completed using file path", operation)
        return file_path, Path(file_path).name
    
    else:
        logger.warning(f"{operation}: Neither file nor file_path provided")
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file' (upload) or 'file_path' (query parameter)"
        )

# ==========================================
# API 1: EXTRACT
# ==========================================
@router.post("/extract")
async def extract_cv(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Query(None, description="Path to CV file"),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Extract CV information from file."""
    
    logger.info("Starting CV extraction")
    logger.info(
        "extract_cv called with file_present=%s file_path_present=%s",
        bool(file),
        bool(file_path),
    )
    
    try:
        processed_file_path, filename = await _validate_and_get_file_path(
            file, file_path, "Extract"
        )
        
        logger.info(f"Calling agent to extract CV from: {processed_file_path}")
        extraction_message = "Extract all information from this CV in structured format"
        
        from starlette.concurrency import run_in_threadpool
        extracted_data = await run_in_threadpool(
            _get_agent().extract_cv,
            file_path=processed_file_path,
            message=extraction_message,
            output_schema=CVInformation
        )
        
        logger.info(f"CV extraction successful for: {filename}")    
        
        # Save extracted data with timestamp folder and candidate+position filename
        candidate_name = extracted_data.personal_info.name if extracted_data.personal_info.name else "Unknown"
        position = extracted_data.experiences[0].job_title if extracted_data.experiences and len(extracted_data.experiences) > 0 else ""
        
        extraction_dir, _ = _get_result_folders()
        file_identifier = f"{candidate_name}_{position}".replace(" ", "_").replace("/", "_")
        if file_identifier.endswith("_"):
            file_identifier = file_identifier.rstrip("_")
        extract_path = extraction_dir / f"{file_identifier}_extraction.json"
        
        with open(extract_path, "w", encoding="utf-8") as f:
            f.write(extracted_data.model_dump_json(indent=2))
        
        logger.info(f"Extracted data saved: {extract_path}")
        logger.info("CV extraction response prepared successfully")
        
        # Save structured candidate profile into the SQLite database
        email = str(extracted_data.personal_info.email) if extracted_data.personal_info.email else None
        phone = extracted_data.personal_info.phone if extracted_data.personal_info.phone else None
        candidate_id = get_background_job_manager().save_candidate(
            tenant_id=tenant.tenant_id,
            name=candidate_name,
            email=email,
            phone=phone,
            extracted_data_json=extracted_data.model_dump_json(),
            file_path=processed_file_path,
        )
        logger.info(f"Candidate profile saved in database with candidate_id={candidate_id}")
        
        return {
            "message": "CV extraction successful",
            "candidate_id": candidate_id,
            "filename": filename,
            "upload_path": processed_file_path,
            "data": extracted_data.model_dump(),
            "extract_path": str(extract_path),
            "result_folder": str(extraction_dir)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CV extraction failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

# ==========================================
# API 2: ANALYZE
# ==========================================
@router.post("/analyze")
async def analyze_cv(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Query(None, description="Path to CV file"),
    cv_data: Optional[str] = Form(None, description="CVInformation as JSON string"),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """Analyze CV and get recruiter insights."""
    
    logger.info("Starting CV analysis")
    logger.info(
        "analyze_cv called with file_present=%s file_path_present=%s cv_data_present=%s",
        bool(file),
        bool(file_path),
        bool(cv_data),
    )
    
    processed_file_path = None
    try:
        # Prefer file input when a file is provided.
        # This avoids accidental 400s when a form also submits a stale or malformed cv_data field.
        if file or file_path:
            logger.info("Extracting CV before analysis")
            
            # Validate and get file path
            processed_file_path, filename = await _validate_and_get_file_path(
                file, file_path, "Analyze"
            )
            
            # Extract CV
            extraction_message = "Extract all information from this CV in structured format"
            from starlette.concurrency import run_in_threadpool
            cv_data = await run_in_threadpool(
                _get_agent().extract_cv,
                file_path=processed_file_path,
                message=extraction_message,
                output_schema=CVInformation
            )
            
            candidate_name = cv_data.personal_info.name
            logger.info("Extraction completed for analysis using file input")

        # Otherwise, use provided CV JSON payload
        elif cv_data:
            try:
                cv_data = CVInformation.model_validate_json(cv_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid CV JSON: {str(e)}")
            logger.info(f"Analyzing provided CVInformation for: {cv_data.personal_info.name}")
            logger.info("Using provided CVInformation payload")
            candidate_name = cv_data.personal_info.name
        
        else:
            logger.warning("No input provided for analysis")
            raise HTTPException(
                status_code=400,
                detail="Provide either 'file', 'file_path', or CVInformation JSON"
            )
        
        # Save or update candidate details in SQL
        email = str(cv_data.personal_info.email) if cv_data.personal_info.email else None
        phone = cv_data.personal_info.phone if cv_data.personal_info.phone else None
        candidate_id = get_background_job_manager().save_candidate(
            tenant_id=tenant.tenant_id,
            name=candidate_name,
            email=email,
            phone=phone,
            extracted_data_json=cv_data.model_dump_json(),
            file_path=processed_file_path,
        )
        
        # Analyze CV
        logger.info(f"Calling agent to analyze CV for: {candidate_name}")
        analysis_message = "Analyze this CV and provide recruiter insights"
        from starlette.concurrency import run_in_threadpool
        analysis_result = await run_in_threadpool(
            _get_agent().analyze_cv,
            cv_information=cv_data,
            output_schema=BaseCandidateAnalysis,
            message=analysis_message
        )
        
        logger.info(f"CV analysis successful for: {candidate_name}")
        
        # Save analysis with timestamp folder and candidate+position filename
        position = cv_data.experiences[0].job_title if cv_data.experiences and len(cv_data.experiences) > 0 else ""
        _, analysis_dir = _get_result_folders()
        file_identifier = f"{candidate_name}_{position}".replace(" ", "_").replace("/", "_")
        if file_identifier.endswith("_"):
            file_identifier = file_identifier.rstrip("_")
        analyze_path = analysis_dir / f"{file_identifier}_analysis.json"
        
        with open(analyze_path, "w", encoding="utf-8") as f:
            f.write(analysis_result.model_dump_json(indent=2))
        
        logger.info(f"Analysis saved: {analyze_path}")
        logger.info("CV analysis response prepared successfully")
        
        return {
            "message": "CV analysis successful",
            "candidate_id": candidate_id,
            "candidate": candidate_name,
            "position": position,
            "analysis": analysis_result.model_dump(),
            "analyze_path": str(analyze_path),
            "result_folder": str(analysis_dir)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CV analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/candidates")
async def list_candidates(
    tenant: TenantContext = Depends(get_tenant_context)
):
    """List all candidate profiles parsed under a specific tenant."""
    logger.info("Listing candidate profiles for tenant %s", tenant.tenant_id)
    try:
        manager = get_background_job_manager()
        candidates = manager.list_candidates_for_tenant(tenant.tenant_id)
        return {"candidates": candidates}
    except Exception as exc:
        logger.error("Failed to list candidates: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve candidates")


@router.get("/candidates/{candidate_id}/file")
async def get_candidate_file_route(
    candidate_id: str,
    tenant: TenantContext = Depends(get_tenant_context)
):
    """Retrieve original CV file by candidate ID."""
    logger.info("Retrieving CV file for candidate %s (tenant %s)", candidate_id, tenant.tenant_id)
    manager = get_background_job_manager()
    candidate = manager.get_candidate(candidate_id)
    if not candidate or candidate["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    file_path_str = candidate.get("file_path")
    filepath = None
    if file_path_str:
        filepath = Path(file_path_str)

    # Fallback 1: Scan UPLOAD_BASE_DIR recursively for files containing candidate name
    if not filepath or not filepath.exists() or not filepath.is_file():
        sanitized_cand_name = _sanitize_filename(candidate["name"]).lower()
        found_files = []
        for p in UPLOAD_BASE_DIR.rglob("*"):
            if p.is_file() and sanitized_cand_name in p.name.lower():
                found_files.append(p)
        
        if found_files:
            found_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            filepath = found_files[0]
            logger.info("Found matching legacy CV file via disk scan: %s", filepath)

    # Fallback 2: Generate dynamic text file fallback with candidate details
    if not filepath or not filepath.exists() or not filepath.is_file():
        logger.info("No raw CV file found for candidate %s on disk. Serving compiler fallback text file.", candidate_id)
        content = f"CANDIDATE RESUME PROFILE\n" \
                  f"========================\n\n" \
                  f"Name:  {candidate['name']}\n" \
                  f"Email: {candidate['email'] or 'N/A'}\n" \
                  f"Phone: {candidate['phone'] or 'N/A'}\n\n" \
                  f"----------------------------------------\n" \
                  f"Note: This candidate profile was saved before the file-tracking feature was added, " \
                  f"or the original uploaded PDF resume has been removed.\n" \
                  f"You can still run AI matching and generation using this profile's structured data.\n" \
                  f"----------------------------------------\n"
        
        # Save to temporary text file
        temp_file = tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False, encoding="utf-8")
        temp_file.write(content)
        temp_file.close()
        return FileResponse(temp_file.name, media_type="text/plain", filename=f"{_sanitize_filename(candidate['name'])}_fallback.txt")

    return FileResponse(filepath)