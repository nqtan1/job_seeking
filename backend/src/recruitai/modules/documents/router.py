"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.errors import (
    NotFound,
    Unauthorized,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.ratelimit import limit_ai
from recruitai.core.storage import Storage, get_storage_dependency
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.documents import service
from recruitai.modules.documents.schemas import (
    DocumentListItem,
    DocumentOut,
    DocumentUploadResponse,
    RotateIn,
    SignatureOut,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentUploadResponse,
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def upload_document(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
    kind: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> DocumentUploadResponse:
    data = await file.read()
    document = await service.upload(
        db, storage, org_id=ctx.org_id, uploaded_by=ctx.user_id, kind=kind, data=data
    )
    return DocumentUploadResponse(document_id=document.id)


@router.get(
    "", response_model=list[DocumentListItem], responses=problem_responses(Unauthorized)
)
async def list_documents(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    kind: Annotated[list[str] | None, Query()] = None,
) -> list[DocumentListItem]:
    rows = await service.list_documents(
        db, org_id=ctx.org_id, kinds=kind or ["cv", "letter_pdf", "attachment"]
    )
    return [
        DocumentListItem(
            document_id=d.id,
            kind=d.kind,
            mime=d.mime,
            size=d.size,
            created_at=d.created_at,
        )
        for d in rows
    ]


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_document(
    document_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> DocumentOut:
    document, url = await service.get_document_with_url(
        db, storage, org_id=ctx.org_id, document_id=document_id
    )
    return DocumentOut(
        document_id=document.id,
        kind=document.kind,
        mime=document.mime,
        size=document.size,
        download_url=url,
    )


signature_router = APIRouter(prefix="/api/v1/signature", tags=["signature"])


@signature_router.get(
    "",
    response_model=SignatureOut | None,
    responses=problem_responses(Unauthorized),
)
async def get_signature(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> SignatureOut | None:
    return await service.get_signature(db, storage, org_id=ctx.org_id)


@signature_router.put(
    "",
    response_model=SignatureOut,
    # App Check + rate limit: decoding an image or PDF is CPU-heavy (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(Unauthorized, ValidationFailed),
)
async def put_signature(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
    file: Annotated[UploadFile, File()],
) -> SignatureOut:
    data = await file.read()
    return await service.set_signature(
        db, storage, org_id=ctx.org_id, user_id=ctx.user_id, data=data
    )


@signature_router.post(
    "/rotate",
    response_model=SignatureOut,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(Unauthorized, NotFound),
)
async def rotate_signature(
    body: RotateIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> SignatureOut:
    return await service.rotate_signature(
        db, storage, org_id=ctx.org_id, degrees=body.degrees
    )


@signature_router.delete("", status_code=204, responses=problem_responses(Unauthorized))
async def delete_signature(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> Response:
    await service.delete_signature(db, storage, org_id=ctx.org_id)
    return Response(status_code=204)
