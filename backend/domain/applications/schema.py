from typing import Optional
from pydantic import BaseModel, Field

class ApplicationBase(BaseModel):
    company_name: str = Field(..., description="The name of the company applied to.")
    source: str = Field(..., description="Source of the job posting (linkedin, indeed, referral, company_site, other).")
    applied_date: str = Field(..., description="The date applied (ISO format YYYY-MM-DD).")
    status: str = Field("to_apply", description="Status of the application (to_apply, applied, in_review, interview, offer, rejected, ghosted).")
    jd_summary: Optional[str] = Field(None, description="Summary or notes related to the job description.")
    recruiter_response: Optional[str] = Field(None, description="Recruiter response details/notes.")
    cv_file: Optional[str] = Field(None, description="Link or path to the uploaded CV file.")
    cover_letter_file: Optional[str] = Field(None, description="Link or path to the uploaded cover letter.")
    special_documents: Optional[str] = Field(None, description="JSON list of special document paths/links (portfolio, certificates, etc.).")
    document_prep_completed_at: Optional[str] = Field(None, description="Timestamp when documents selections were finalized.")
    applied_confirmed_at: Optional[str] = Field(None, description="Timestamp when the application was physically submitted.")

class ApplicationCreate(ApplicationBase):
    pass

class ApplicationUpdate(ApplicationBase):
    pass

class ApplicationResponse(ApplicationBase):
    application_id: str = Field(..., description="The unique ID of the application.")
    tenant_id: str = Field(..., description="The multi-tenant ID.")
    created_at: str = Field(..., description="Timestamp of creation.")
    updated_at: str = Field(..., description="Timestamp of last update.")
