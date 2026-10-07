"""HTTP only: parse the request, call the service, map the result to a response schema."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import LLMGateway
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.errors import (
    NotFound,
    Unauthorized,
    UpstreamUnavailable,
    ValidationFailed,
    problem_responses,
)
from recruitai.core.ratelimit import limit_ai
from recruitai.core.storage import Storage, get_storage_dependency
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.applications import service as applications
from recruitai.modules.letters import service
from recruitai.modules.letters.models import Letter, LetterVersion
from recruitai.modules.letters.schemas import (
    AssistIn,
    AssistOut,
    BlockEditIn,
    BlockName,
    BlockRegenerateIn,
    ExportOut,
    LetterCheck,
    LetterContent,
    LetterIn,
    LetterOut,
    PdfLinkOut,
    RenderAccepted,
    VersionOut,
)

router = APIRouter(prefix="/api/v1/letters", tags=["letters"])


def _out(letter: Letter) -> LetterOut:
    # Values come from DB CHECK constraints, so they always fit the Literal types.
    return LetterOut.model_validate(
        {
            "id": letter.id,
            "job_id": letter.job_id,
            "kind": letter.kind,
            "template": letter.template,
            "language": letter.language,
            "tone": letter.tone,
            "length": letter.length,
            "company_type": letter.company_type,
            "status": letter.status,
            "render_status": letter.render_status,
            "pdf_document_id": letter.pdf_document_id,
            "pdf_filename": service.pdf_filename(letter),
            "content": letter.content,
            "created_at": letter.created_at,
            "updated_at": letter.updated_at,
        }
    )


def _version_out(version: LetterVersion) -> VersionOut:
    return VersionOut(
        n=version.n,
        content=LetterContent.model_validate(version.content),
        created_at=version.created_at,
    )


@router.post(
    "",
    status_code=201,
    response_model=LetterOut,
    # App Check: generating a letter costs an LLM call (core/app_check.py).
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def create_letter(
    body: LetterIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> LetterOut:
    letter = await service.generate(db, llm, org_id=ctx.org_id, **body.model_dump())
    return _out(letter)


@router.get(
    "", response_model=list[LetterOut], responses=problem_responses(Unauthorized)
)
async def list_letters(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    job_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LetterOut]:
    letters = await service.list_letters(
        db, org_id=ctx.org_id, job_id=job_id, limit=limit, offset=offset
    )
    return [_out(letter) for letter in letters]


@router.get(
    "/{letter_id}",
    response_model=LetterOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_letter(
    letter_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LetterOut:
    return _out(await service.get_letter(db, org_id=ctx.org_id, letter_id=letter_id))


@router.delete(
    "/{letter_id}",
    status_code=204,
    responses=problem_responses(Unauthorized, NotFound),
)
async def delete_letter(
    letter_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> Response:
    letter = await service.get_letter(db, org_id=ctx.org_id, letter_id=letter_id)
    sent = (
        letter.pdf_document_id is not None
        and await applications.document_is_attached(
            db, org_id=ctx.org_id, document_id=letter.pdf_document_id
        )
    )
    await service.delete_letter(
        db, storage, org_id=ctx.org_id, letter_id=letter_id, keep_pdf=sent
    )
    return Response(status_code=204)


@router.patch(
    "/{letter_id}/blocks/{block}",
    response_model=LetterOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def edit_block(
    letter_id: UUID,
    block: BlockName,
    body: BlockEditIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LetterOut:
    letter = await service.edit_block(
        db,
        org_id=ctx.org_id,
        letter_id=letter_id,
        block=block,
        text=body.text,
        index=body.index,
    )
    return _out(letter)


@router.post(
    "/{letter_id}/blocks/{block}/regenerate",
    response_model=LetterOut,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def regenerate_block(
    letter_id: UUID,
    block: BlockName,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
    body: BlockRegenerateIn | None = None,
) -> LetterOut:
    letter = await service.regenerate_block(
        db,
        llm,
        org_id=ctx.org_id,
        letter_id=letter_id,
        block=block,
        index=body.index if body else None,
    )
    return _out(letter)


@router.get(
    "/{letter_id}/versions",
    response_model=list[VersionOut],
    responses=problem_responses(Unauthorized, NotFound),
)
async def list_versions(
    letter_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[VersionOut]:
    versions = await service.list_versions(db, org_id=ctx.org_id, letter_id=letter_id)
    return [_version_out(v) for v in versions]


@router.post(
    "/{letter_id}/versions/{n}/restore",
    response_model=LetterOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def restore_version(
    letter_id: UUID,
    n: int,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LetterOut:
    letter = await service.restore_version(
        db, org_id=ctx.org_id, letter_id=letter_id, n=n
    )
    return _out(letter)


@router.post(
    "/{letter_id}/render",
    status_code=202,
    response_model=RenderAccepted,
    responses=problem_responses(Unauthorized, NotFound),
)
async def render_letter(
    letter_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RenderAccepted:
    """Queue the PDF render; poll ``status_url`` until ``done`` (it then carries the signed
    ``download_url``)."""
    task_id = await service.request_render(db, org_id=ctx.org_id, letter_id=letter_id)
    return RenderAccepted(task_id=task_id, status_url=f"/api/v1/tasks/{task_id}")


@router.get(
    "/{letter_id}/export",
    response_model=ExportOut,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def export_letter(
    letter_id: UUID,
    fmt: Annotated[Literal["text", "email"], Query(alias="format")],
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExportOut:
    subject, body = await service.export_letter(
        db, org_id=ctx.org_id, letter_id=letter_id, fmt=fmt
    )
    return ExportOut(format=fmt, subject=subject, body=body)


@router.get(
    "/{letter_id}/check",
    response_model=LetterCheck,
    responses=problem_responses(Unauthorized, NotFound, ValidationFailed),
)
async def check_letter(
    letter_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LetterCheck:
    """Claims the profile doesn't back up, plus the quality panel. No model call."""
    return await service.check_letter(db, org_id=ctx.org_id, letter_id=letter_id)


@router.post(
    "/{letter_id}/assist",
    response_model=AssistOut,
    dependencies=[Depends(verify_app_check), Depends(limit_ai)],
    responses=problem_responses(
        Unauthorized, NotFound, ValidationFailed, UpstreamUnavailable
    ),
)
async def assist(
    letter_id: UUID,
    body: AssistIn,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
) -> AssistOut:
    """Suggest a rewrite of a selection (shorten, more formal, more concrete, add a metric,
    fix grammar). Saves nothing: apply it with ``PATCH .../blocks/{block}``."""
    suggestion = await service.assist(
        db,
        llm,
        org_id=ctx.org_id,
        letter_id=letter_id,
        block=body.block,
        selection=body.selection,
        action=body.action,
    )
    return AssistOut(suggestion=suggestion)


@router.get(
    "/{letter_id}/pdf",
    response_model=PdfLinkOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def pdf_link(
    letter_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> PdfLinkOut:
    """Signed, inline link to the rendered PDF (named like the downloaded file)."""
    url = await service.pdf_link(db, storage, org_id=ctx.org_id, letter_id=letter_id)
    return PdfLinkOut(download_url=url)
