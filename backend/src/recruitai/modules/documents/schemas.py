from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
