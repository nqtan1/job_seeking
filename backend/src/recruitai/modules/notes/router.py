"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings, get_settings
from recruitai.core.db import get_db
from recruitai.core.errors import (
    NotFound,
    Unauthorized,
    UpstreamUnavailable,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.notes import service
from recruitai.modules.notes.models import Note
from recruitai.modules.notes.schemas import NoteIn, NoteOut


def require_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    if not settings.notes_enabled:
        raise UpstreamUnavailable(
            "Notes are switched off for now.", code="notes_disabled"
        )


router = APIRouter(
    prefix="/api/v1/notes", tags=["notes"], dependencies=[Depends(require_enabled)]
)
Ctx = Annotated[OrgContext, Depends(get_org_context)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "",
    status_code=201,
    response_model=NoteOut,
    responses=problem_responses(Unauthorized, ValidationFailed, UpstreamUnavailable),
)
async def create_note(body: NoteIn, ctx: Ctx, db: Db) -> Note:
    return await service.create_note(db, org_id=ctx.org_id, data=body)


@router.get("", response_model=list[NoteOut], responses=problem_responses(Unauthorized))
async def list_notes(
    ctx: Ctx,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Note]:
    return await service.list_notes(db, org_id=ctx.org_id, limit=limit, offset=offset)


@router.get(
    "/{note_id}",
    response_model=NoteOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def get_note(note_id: UUID, ctx: Ctx, db: Db) -> Note:
    return await service.get_note(db, org_id=ctx.org_id, note_id=note_id)


@router.delete(
    "/{note_id}", status_code=204, responses=problem_responses(Unauthorized, NotFound)
)
async def delete_note(note_id: UUID, ctx: Ctx, db: Db) -> Response:
    await service.delete_note(db, org_id=ctx.org_id, note_id=note_id)
    return Response(status_code=204)
