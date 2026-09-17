import os
import re
import json
import unicodedata
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, status, Query
from fastapi.responses import FileResponse

from core.auth import TenantContext, get_tenant_context
from workers.background import get_background_job_manager
from utils.logger import get_logger
from applications.schema import ApplicationCreate, ApplicationUpdate, ApplicationResponse

logger = get_logger(name="applications.route", log_file="applications_api.log", level="INFO")

router = APIRouter()

# Setup Upload Directory
data_dir_env = os.getenv("DATA_DIR")
if data_dir_env:
    DB_BASE_DIR = Path(data_dir_env)
else:
    DB_BASE_DIR = Path(__file__).parent.parent / "db"

UPLOAD_BASE_DIR = DB_BASE_DIR / "applications" / "uploads"
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing/replacing special characters.
    Handles Unicode characters like accents.
    """
    filename = unicodedata.normalize('NFKD', filename)
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    filename = re.sub(r'[^\w\s.-]', '_', filename)
    filename = re.sub(r'[\s_]+', '_', filename)
    filename = filename.rstrip('_')
    return filename


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    request: ApplicationCreate,
    tenant: TenantContext = Depends(get_tenant_context)
):
    logger.info("Creating job application for tenant %s, company %s", tenant.tenant_id, request.company_name)
    try:
        manager = get_background_job_manager()
        app_id = manager.save_application(
            tenant_id=tenant.tenant_id,
            company_name=request.company_name,
            source=request.source,
            applied_date=request.applied_date,
            status=request.status,
            jd_summary=request.jd_summary,
            recruiter_response=request.recruiter_response,
            cv_file=request.cv_file,
            cover_letter_file=request.cover_letter_file,
            special_documents=request.special_documents,
            document_prep_completed_at=request.document_prep_completed_at,
            applied_confirmed_at=request.applied_confirmed_at
        )
        saved = manager.get_application(app_id)
        if not saved:
            raise HTTPException(status_code=500, detail="Failed to retrieve created application")
        return ApplicationResponse(**saved)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to create application: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while creating application")


@router.get("", response_model=List[ApplicationResponse])
async def list_applications(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    sort_by_date: str = Query("desc", description="Sort by applied date: 'asc' or 'desc'"),
    tenant: TenantContext = Depends(get_tenant_context)
):
    logger.info("Listing job applications for tenant %s", tenant.tenant_id)
    try:
        manager = get_background_job_manager()
        apps = manager.list_applications_for_tenant(
            tenant_id=tenant.tenant_id,
            status=status,
            source=source,
            sort_by_date=sort_by_date
        )
        return [ApplicationResponse(**app) for app in apps]
    except Exception as exc:
        logger.error("Failed to list applications: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while listing applications")


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: str,
    tenant: TenantContext = Depends(get_tenant_context)
):
    logger.info("Getting job application %s for tenant %s", application_id, tenant.tenant_id)
    manager = get_background_job_manager()
    app = manager.get_application(application_id)
    if not app or app["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Job application not found")
    return ApplicationResponse(**app)


@router.put("/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: str,
    request: ApplicationUpdate,
    tenant: TenantContext = Depends(get_tenant_context)
):
    logger.info("Updating job application %s for tenant %s", application_id, tenant.tenant_id)
    manager = get_background_job_manager()
    app = manager.get_application(application_id)
    if not app or app["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Job application not found")

    try:
        success = manager.update_application(
            application_id=application_id,
            company_name=request.company_name,
            source=request.source,
            applied_date=request.applied_date,
            status=request.status,
            jd_summary=request.jd_summary,
            recruiter_response=request.recruiter_response,
            cv_file=request.cv_file,
            cover_letter_file=request.cover_letter_file,
            special_documents=request.special_documents,
            document_prep_completed_at=request.document_prep_completed_at,
            applied_confirmed_at=request.applied_confirmed_at
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update application")
        
        updated = manager.get_application(application_id)
        return ApplicationResponse(**updated)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update application: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while updating application")


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: str,
    tenant: TenantContext = Depends(get_tenant_context)
):
    logger.info("Deleting job application %s for tenant %s", application_id, tenant.tenant_id)
    manager = get_background_job_manager()
    app = manager.get_application(application_id)
    if not app or app["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Job application not found")

    # Optional: Delete associated uploaded files if they exist locally
    for file_field in ["cv_file", "cover_letter_file"]:
        file_url = app.get(file_field)
        if file_url and file_url.startswith("/api/applications/files/"):
            filename = file_url.split("/")[-1]
            filepath = UPLOAD_BASE_DIR / filename
            if filepath.exists():
                try:
                    filepath.unlink()
                    logger.info("Deleted associated file: %s", filepath)
                except Exception as exc:
                    logger.warning("Failed to delete associated file %s: %s", filepath, str(exc))

    # Also delete any special documents if they are stored locally
    special_docs_str = app.get("special_documents")
    if special_docs_str:
        try:
            docs = json.loads(special_docs_str)
            for file_url in docs:
                if file_url.startswith("/api/applications/files/"):
                    filename = file_url.split("/")[-1]
                    filepath = UPLOAD_BASE_DIR / filename
                    if filepath.exists():
                        filepath.unlink()
                        logger.info("Deleted associated special document: %s", filepath)
        except Exception as exc:
            logger.warning("Failed to delete associated special documents: %s", str(exc))

    success = manager.delete_application(application_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete application")
    return


@router.post("/{application_id}/upload", response_model=ApplicationResponse)
async def upload_application_file(
    application_id: str,
    file_type: str = Form(..., description="Type of file being uploaded (cv or cover_letter)"),
    file: UploadFile = File(...),
    tenant: TenantContext = Depends(get_tenant_context)
):
    logger.info("Uploading %s for job application %s (tenant %s)", file_type, application_id, tenant.tenant_id)
    if file_type not in ("cv", "cover_letter"):
        raise HTTPException(status_code=400, detail="Invalid file_type. Must be 'cv' or 'cover_letter'")

    manager = get_background_job_manager()
    app = manager.get_application(application_id)
    if not app or app["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Job application not found")

    sanitized_name = _sanitize_filename(file.filename)
    saved_filename = f"{application_id}_{file_type}_{sanitized_name}"
    filepath = UPLOAD_BASE_DIR / saved_filename

    # Read and save file content
    try:
        content = await file.read()
        filepath.write_bytes(content)
    except Exception as exc:
        logger.error("Failed to write uploaded file to disk: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # Update DB application record with the file path URL
    file_url = f"/api/applications/files/{saved_filename}"
    
    cv_file = file_url if file_type == "cv" else app["cv_file"]
    cover_letter_file = file_url if file_type == "cover_letter" else app["cover_letter_file"]

    try:
        manager.update_application(
            application_id=application_id,
            company_name=app["company_name"],
            source=app["source"],
            applied_date=app["applied_date"],
            status=app["status"],
            jd_summary=app["jd_summary"],
            recruiter_response=app["recruiter_response"],
            cv_file=cv_file,
            cover_letter_file=cover_letter_file,
            special_documents=app.get("special_documents"),
            document_prep_completed_at=app.get("document_prep_completed_at"),
            applied_confirmed_at=app.get("applied_confirmed_at")
        )
        updated = manager.get_application(application_id)
        return ApplicationResponse(**updated)
    except Exception as exc:
        logger.error("Failed to update application file references: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update database record after upload")


@router.post("/{application_id}/upload-special", response_model=ApplicationResponse)
async def upload_special_documents(
    application_id: str,
    files: List[UploadFile] = File(...),
    tenant: TenantContext = Depends(get_tenant_context)
):
    logger.info("Uploading special documents for job application %s (tenant %s)", application_id, tenant.tenant_id)
    manager = get_background_job_manager()
    app = manager.get_application(application_id)
    if not app or app["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Job application not found")

    existing_special_docs_str = app.get("special_documents")
    existing_docs = []
    if existing_special_docs_str:
        try:
            existing_docs = json.loads(existing_special_docs_str)
        except Exception:
            existing_docs = [existing_special_docs_str] if existing_special_docs_str else []

    uploaded_urls = []
    for file in files:
        sanitized_name = _sanitize_filename(file.filename)
        saved_filename = f"{application_id}_special_{sanitized_name}"
        filepath = UPLOAD_BASE_DIR / saved_filename

        try:
            content = await file.read()
            filepath.write_bytes(content)
            file_url = f"/api/applications/files/{saved_filename}"
            uploaded_urls.append(file_url)
        except Exception as exc:
            logger.error("Failed to write uploaded special file to disk: %s", str(exc), exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    new_docs_list = existing_docs + uploaded_urls
    new_docs_str = json.dumps(new_docs_list)

    try:
        manager.update_application(
            application_id=application_id,
            company_name=app["company_name"],
            source=app["source"],
            applied_date=app["applied_date"],
            status=app["status"],
            jd_summary=app["jd_summary"],
            recruiter_response=app["recruiter_response"],
            cv_file=app["cv_file"],
            cover_letter_file=app["cover_letter_file"],
            special_documents=new_docs_str,
            document_prep_completed_at=app.get("document_prep_completed_at"),
            applied_confirmed_at=app.get("applied_confirmed_at")
        )
        updated = manager.get_application(application_id)
        return ApplicationResponse(**updated)
    except Exception as exc:
        logger.error("Failed to update application special documents: %s", str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update database record after upload")


@router.get("/files/{filename}")
async def get_application_file(
    filename: str,
    tenant: TenantContext = Depends(get_tenant_context)
):
    # Retrieve file safely.
    parts = filename.split("_", 2)
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Invalid filename format")
    
    application_id = parts[0]
    manager = get_background_job_manager()
    app = manager.get_application(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="File not found")
    if app["tenant_id"] != tenant.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to requested file")

    filepath = UPLOAD_BASE_DIR / filename
    if not filepath.exists() or not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(filepath)
