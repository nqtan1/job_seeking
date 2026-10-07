"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import get_db
from recruitai.core.errors import (
    NotFound,
    Unauthorized,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.storage import Storage, get_storage_dependency
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.applications import service
from recruitai.modules.applications.models import Application, ApplicationEvent
from recruitai.modules.applications.schemas import (
    ApplicationDocumentIn,
    ApplicationDocumentOut,
    ApplicationIn,
    ApplicationOut,
    ApplicationUpdate,
    EventOut,
    Status,
    StatusChangeIn,
    next_statuses,
)

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])


def _out(a: Application) -> ApplicationOut:
    # status/source come from DB CHECK constraints, so they always fit the Literal types.
    return ApplicationOut.model_validate(
        {
            "id": a.id,
            "job_id": a.job_id,
            "company_name": a.company_name,
            "job_title": a.job_title,
            "source": a.source,
            "status": a.status,
            "next_statuses": next_statuses(a.status),
            "applied_at": a.applied_at,
            "notes": a.notes,
            "interview_at": a.interview_at,
            "contact": a.contact,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }
    )


def _event_out(e: ApplicationEvent) -> EventOut:
    return EventOut.model_validate(
        {
            "id": e.id,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "at": e.at,
            "note": e.note,
        }
    )


@router.post(
    "",
    status_code=201,
    response_model=ApplicationOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def create_application(
    body: ApplicationIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationOut:
    return _out(await service.create_application(db, org_id=ctx.org_id, data=body))


@router.get(
    "", response_model=list[ApplicationOut], responses=problem_responses(Unauthorized)
)
async def list_applications(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Status | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ApplicationOut]:
    rows = await service.list_applications(
        db, org_id=ctx.org_id, status=status, limit=limit, offset=offset
    )
    return [_out(a) for a in rows]


@router.get(
    "/{application_id}",
    response_model=ApplicationOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_application(
    application_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationOut:
    return _out(
        await service.get_application(
            db, org_id=ctx.org_id, application_id=application_id
        )
    )


@router.patch(
    "/{application_id}",
    response_model=ApplicationOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def update_application(
    application_id: UUID,
    body: ApplicationUpdate,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationOut:
    return _out(
        await service.update_application(
            db, org_id=ctx.org_id, application_id=application_id, changes=body
        )
    )


@router.post(
    "/{application_id}/status",
    response_model=ApplicationOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def change_status(
    application_id: UUID,
    body: StatusChangeIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationOut:
    """Move along the allowed transitions (``next_statuses`` on the application); an illegal
    move is a 422 that lists the allowed ones."""
    return _out(
        await service.change_status(
            db,
            org_id=ctx.org_id,
            application_id=application_id,
            to_status=body.status,
            note=body.note,
        )
    )


@router.get(
    "/{application_id}/events",
    response_model=list[EventOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_events(
    application_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[EventOut]:
    events = await service.list_events(
        db, org_id=ctx.org_id, application_id=application_id
    )
    return [_event_out(e) for e in events]


@router.delete(
    "/{application_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def delete_application(
    application_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.delete_application(
        db, org_id=ctx.org_id, application_id=application_id
    )
    return Response(status_code=204)


@router.get(
    "/{application_id}/documents",
    response_model=list[ApplicationDocumentOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_documents(
    application_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> list[ApplicationDocumentOut]:
    rows = await service.list_documents(
        db, storage, org_id=ctx.org_id, application_id=application_id
    )
    return [
        ApplicationDocumentOut(
            document_id=d.id,
            kind=d.kind,
            mime=d.mime,
            size=d.size,
            created_at=d.created_at,
            filename=name,
            download_url=view,
            save_url=save,
        )
        for d, view, save, name in rows
    ]


@router.post(
    "/{application_id}/documents",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def attach_document(
    application_id: UUID,
    body: ApplicationDocumentIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.attach_document(
        db,
        org_id=ctx.org_id,
        application_id=application_id,
        document_id=body.document_id,
    )
    return Response(status_code=204)


@router.delete(
    "/{application_id}/documents/{document_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def detach_document(
    application_id: UUID,
    document_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await service.detach_document(
        db,
        org_id=ctx.org_id,
        application_id=application_id,
        document_id=document_id,
    )
    return Response(status_code=204)
