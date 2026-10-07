"""GET /api/v1/tasks/{id}: reads the task_runs row, never Procrastinate internals directly.
Split from core/tasks.py (FastAPI-dependent) the same way error_handlers.py/storage_routes.py
are split from their framework-free counterparts.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import get_db
from recruitai.core.errors import NotFound, Unauthorized, problem_responses
from recruitai.core.storage import Storage, get_storage_dependency
from recruitai.core.tasks import TaskRun
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.documents import service as documents

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class TaskStatusOut(BaseModel):
    status: str
    result_ref: str | None
    error_code: str | None
    # Set when a finished task produced a file: a signed URL valid for 15 minutes.
    download_url: str | None = None


@router.get(
    "/{task_id}",
    response_model=TaskStatusOut,
    responses=problem_responses(Unauthorized, NotFound),
)
async def read_task(
    task_id: UUID,
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[Storage, Depends(get_storage_dependency)],
) -> TaskStatusOut:
    task_run = (
        await db.execute(
            select(TaskRun).where(TaskRun.id == task_id, TaskRun.org_id == ctx.org_id)
        )
    ).scalar_one_or_none()
    if task_run is None:
        raise NotFound("Task not found.")
    return TaskStatusOut(
        status=task_run.status,
        result_ref=task_run.result_ref,
        error_code=task_run.error_code,
        download_url=await _download_url(db, storage, task_run, ctx.org_id),
    )


async def _download_url(
    db: AsyncSession, storage: Storage, task_run: TaskRun, org_id: UUID
) -> str | None:
    """A done task whose ``result_ref`` is one of *this org's* documents gets a signed URL.
    The lookup is org-scoped, so a ref to anyone else's file yields nothing."""
    if task_run.status != "done" or not task_run.result_ref:
        return None
    try:
        document_id = UUID(task_run.result_ref)
        _, url = await documents.get_document_with_url(
            db, storage, org_id=org_id, document_id=document_id
        )
    except (ValueError, NotFound):
        return None
    return url
