from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from recruitai.modules.documents.signature_spec import Issue


class DocumentUploadResponse(BaseModel):
    document_id: UUID


class DocumentOut(BaseModel):
    document_id: UUID
    kind: str
    mime: str
    size: int
    download_url: str


class DocumentListItem(BaseModel):
    document_id: UUID
    kind: str
    mime: str
    size: int
    created_at: datetime


class SignatureLimits(BaseModel):
    min_width_mm: int
    max_width_mm: int
    max_height_mm: int
    min_dpi: int


class SignatureOut(BaseModel):
    document_id: UUID
    url: str  # short-lived signed URL of the PNG
    width_px: int
    height_px: int
    aspect: float
    issues: list[Issue]
    recommended_width_mm: int
    limits: SignatureLimits


class RotateIn(BaseModel):
    degrees: int = Field(ge=-180, le=180)  # clockwise positive
