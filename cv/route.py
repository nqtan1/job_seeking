import json
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from typing import Optional
from dotenv import load_dotenv
import unicodedata
import re

from utils.logger import get_logger 
from cv.agent import CVAnalysisAgent 
from cv.schema import CVInformation, BaseCandidateAnalysis

logger = get_logger(name="cv.route", log_file="cv_api.log", level="DEBUG")
load_dotenv()

router = APIRouter()
agent = CVAnalysisAgent()

# Allowed file extensions 
ALLOWED_EXTENSIONS = {".pdf", ".img", ".txt", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 10 * 1024 * 1024
UPLOAD_BASE_DIR = Path(__file__).parent.parent / "db/cv/uploads"
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
    
    extraction_dir = Path(__file__).parent.parent / "db/cv/extract" / timestamp
    analysis_dir = Path(__file__).parent.parent / "db/cv/analyze" / timestamp
    
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
    Validate file and return (file_path, filename)
    
    Args:
        file: Uploaded file object
        file_path: Path to existing file
        operation: Operation name for logging
    
    Returns:
        Tuple of (file_path, filename)
    """
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
        
        logger.debug(f"File saved: {saved_path} (original: {file.filename})")
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
    file_path: Optional[str] = Query(None, description="Path to CV file")
):
    """Extract CV information from file."""
    
    logger.info("Starting CV extraction")
    
    try:
        processed_file_path, filename = await _validate_and_get_file_path(
            file, file_path, "Extract"
        )
        
        logger.debug(f"Calling agent to extract CV from: {processed_file_path}")
        extraction_message = "Extract all information from this CV in structured format"
        extracted_data = agent.extract_cv(
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
        
        logger.debug(f"Extracted data saved: {extract_path}")
        
        return {
            "message": "CV extraction successful",
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
    cv_data: Optional[str] = Form(None, description="CVInformation as JSON string")
):
    """Analyze CV and get recruiter insights."""
    
    logger.info("Starting CV analysis")
    
    try:
        # Convert dict to CVInformation if provided
        if cv_data:
            cv_data = CVInformation(**cv_data)
            logger.info(f"Analyzing provided CVInformation for: {cv_data.personal_info.name}")
            candidate_name = cv_data.personal_info.name
        
        # Otherwise, extract from file first
        elif file or file_path:
            logger.debug("Extracting CV before analysis")
            
            # Validate and get file path
            processed_file_path, filename = await _validate_and_get_file_path(
                file, file_path, "Analyze"
            )
            
            # Extract CV
            extraction_message = "Extract all information from this CV in structured format"
            cv_data = agent.extract_cv(
                file_path=processed_file_path,
                message=extraction_message,
                output_schema=CVInformation
            )
            
            candidate_name = cv_data.personal_info.name
            logger.debug(f"Extraction completed for analysis")
        
        else:
            logger.warning("No input provided for analysis")
            raise HTTPException(
                status_code=400,
                detail="Provide either 'file', 'file_path', or CVInformation JSON"
            )
        
        # Analyze CV
        logger.debug(f"Calling agent to analyze CV for: {candidate_name}")
        analysis_message = "Analyze this CV and provide recruiter insights"
        analysis_result = agent.analyze_cv(
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
        
        logger.debug(f"Analysis saved: {analyze_path}")
        
        return {
            "message": "CV analysis successful",
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