"""The application tracker. No FastAPI imports. The status moves only along
``schemas.TRANSITIONS``; every move (and the creation) appends an event, so the timeline is
the complete history."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.filenames import safe_filename
from recruitai.core.storage import Storage
from recruitai.modules.applications import repository
from recruitai.modules.applications.models import Application, ApplicationEvent
from recruitai.modules.applications.schemas import (
    TRANSITIONS,
    ApplicationIn,
    ApplicationUpdate,
    Status,
)
from recruitai.modules.candidates import service as candidates
from recruitai.modules.documents import service as documents
from recruitai.modules.jobs import service as jobs
from recruitai.modules.letters import service as letters


def _today() -> date:
    return datetime.now(UTC).date()


async def create_application(
    db: AsyncSession, *, org_id: UUID, data: ApplicationIn
) -> Application:
    company, title = data.company_name, data.job_title
    if data.job_id is not None:
        job = (await jobs.get_job(db, org_id=org_id, job_id=data.job_id)).data
        company = (
            company or ((job.get("company") or {}).get("name") or "").strip() or None
        )
        title = title or (job.get("title") or "").strip() or None
    if not company:  # a linked job without a company name and none given
        raise ValidationFailed("company_name is required.")
    applied_at = data.applied_at
    if data.status == "applied" and applied_at is None:
        applied_at = _today()
    application = await repository.create(
        db,
        org_id=org_id,
        job_id=data.job_id,
        company_name=company,
        job_title=title,
        source=data.source,
        status=data.status,
        applied_at=applied_at,
        notes=data.notes,
    )
    await db.commit()
    return application


async def get_application(
    db: AsyncSession, *, org_id: UUID, application_id: UUID
) -> Application:
    application = await repository.get(db, org_id=org_id, application_id=application_id)
    if application is None:
        raise NotFound("Application not found.")
    return application


async def list_applications(
    db: AsyncSession,
    *,
    org_id: UUID,
    status: Status | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Application]:
    return await repository.list_for_org(
        db, org_id=org_id, status=status, limit=limit, offset=offset
    )


async def _locked(
    db: AsyncSession, *, org_id: UUID, application_id: UUID
) -> Application:
    application = await repository.get(
        db, org_id=org_id, application_id=application_id, for_update=True
    )
    if application is None:
        raise NotFound("Application not found.")
    return application


async def update_application(
    db: AsyncSession, *, org_id: UUID, application_id: UUID, changes: ApplicationUpdate
) -> Application:
    application = await _locked(db, org_id=org_id, application_id=application_id)
    application = await repository.update(
        db, application, changes.model_dump(exclude_unset=True)
    )
    await db.commit()
    return application


async def change_status(
    db: AsyncSession,
    *,
    org_id: UUID,
    application_id: UUID,
    to_status: Status,
    note: str | None = None,
) -> Application:
    """Validated against the status *as locked now*: of two simultaneous moves, the second
    sees the first's result and is refused if it is no longer legal."""
    application = await _locked(db, org_id=org_id, application_id=application_id)
    current: Status = application.status  # type: ignore[assignment]  # DB CHECK
    allowed = TRANSITIONS[current]
    if to_status not in allowed:
        options = ", ".join(allowed) if allowed else "none (this status is final)"
        raise ValidationFailed(
            f"An application cannot move from '{current}' to '{to_status}'. Allowed: {options}."
        )
    application.status = to_status
    if to_status == "applied" and application.applied_at is None:
        application.applied_at = _today()
    await repository.add_event(
        db,
        application=application,
        from_status=current,
        to_status=to_status,
        note=(note or "").strip() or None,
    )
    await db.flush()
    await db.refresh(application)
    await db.commit()
    return application


async def list_events(
    db: AsyncSession, *, org_id: UUID, application_id: UUID
) -> list[ApplicationEvent]:
    await get_application(db, org_id=org_id, application_id=application_id)  # 404 first
    return await repository.list_events(
        db, org_id=org_id, application_id=application_id
    )


async def delete_application(
    db: AsyncSession, *, org_id: UUID, application_id: UUID
) -> None:
    application = await _locked(db, org_id=org_id, application_id=application_id)
    await repository.delete(db, application)
    await db.commit()


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, Any]]]:
    return {
        "applications": rows_as_dicts(await repository.all_for_org(db, org_id=org_id)),
        "application_events": rows_as_dicts(
            await repository.all_events_for_org(db, org_id=org_id)
        ),
        "application_documents": rows_as_dicts(
            await repository.all_documents_for_org(db, org_id=org_id)
        ),
    }


# What a user can attach: the CV they uploaded, a letter PDF, or any other file.
_ATTACHABLE = ("cv", "letter_pdf", "attachment")


async def attach_document(
    db: AsyncSession, *, org_id: UUID, application_id: UUID, document_id: UUID
) -> None:
    await get_application(db, org_id=org_id, application_id=application_id)
    found = await documents.list_documents(db, org_id=org_id, kinds=list(_ATTACHABLE))
    if document_id not in {d.id for d in found}:
        raise NotFound("Document not found.")
    await repository.attach_document(
        db, org_id=org_id, application_id=application_id, document_id=document_id
    )
    await db.commit()


async def detach_document(
    db: AsyncSession, *, org_id: UUID, application_id: UUID, document_id: UUID
) -> None:
    await get_application(db, org_id=org_id, application_id=application_id)
    await repository.detach_document(
        db, org_id=org_id, application_id=application_id, document_id=document_id
    )
    await db.commit()


async def document_is_attached(
    db: AsyncSession, *, org_id: UUID, document_id: UUID
) -> bool:
    return await repository.document_attached(
        db, org_id=org_id, document_id=document_id
    )


_EXT = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}


async def _document_name(
    db: AsyncSession, *, org_id: UUID, application: Application, document: Any
) -> str:
    """A professional name per file: the letter PDF carries the candidate and company, the CV
    the candidate; anything else falls back to its kind and the company."""
    ext = _EXT.get(document.mime, "txt")
    if document.kind == "letter_pdf":
        name = await letters.pdf_filename_for_document(
            db, org_id=org_id, document_id=document.id
        )
        if name:
            return name
    if document.kind == "cv":
        has_profile = await candidates.has_profile(db, org_id=org_id)
        who = (
            (await candidates.get_profile(db, org_id=org_id)).name
            if has_profile
            else None
        )
        return safe_filename("CV", who, ext=ext)
    label = "Motivation letter" if document.kind == "letter_pdf" else "Document"
    return safe_filename(label, application.company_name, ext=ext)


async def list_documents(
    db: AsyncSession, storage: Storage, *, org_id: UUID, application_id: UUID
) -> list[tuple[Any, str, str, str]]:
    """The attached files: ``(document, view_url, save_url, filename)``. The view URL shows the
    file in the browser, the save URL downloads it; both carry the professional name."""
    application = await get_application(
        db, org_id=org_id, application_id=application_id
    )
    links = await repository.list_documents(
        db, org_id=org_id, application_id=application_id
    )
    out = []
    for link in links:
        document, _ = await documents.get_document_with_url(
            db, storage, org_id=org_id, document_id=link.document_id
        )
        name = await _document_name(
            db, org_id=org_id, application=application, document=document
        )
        _, view = await documents.get_document_with_url(
            db, storage, org_id=org_id, document_id=document.id, filename=name
        )
        _, save = await documents.get_document_with_url(
            db,
            storage,
            org_id=org_id,
            document_id=document.id,
            filename=name,
            attachment=True,
        )
        out.append((document, view, save, name))
    return out


async def count_by_status(db: AsyncSession) -> dict[str, int]:
    rows = await db.execute(
        select(Application.status, func.count()).group_by(Application.status)
    )
    return {status: n for status, n in rows.all()}


FOLLOW_UP_AFTER_DAYS = 7
INTERVIEW_LEAD_DAYS = (3, 1)


@dataclass(frozen=True)
class Reminder:
    org_id: UUID
    kind: str  # "followup" | "interview"
    company: str
    days: int  # followup: days since sent; interview: days until it


async def due_reminders(db: AsyncSession, *, today: date) -> list[Reminder]:
    """Stateless: an item is due on exactly one day (7 days after sending; 3 and 1 days
    before an interview), so a daily run mentions each of them once. Dates are UTC days."""
    out = [
        Reminder(a.org_id, "followup", a.company_name, FOLLOW_UP_AFTER_DAYS)
        for a in await repository.due_for_followup(
            db, sent_on=today - timedelta(days=FOLLOW_UP_AFTER_DAYS)
        )
    ]
    interviews = await repository.interviews_on(
        db, days=[today + timedelta(days=n) for n in INTERVIEW_LEAD_DAYS]
    )
    for a in interviews:
        assert a.interview_at is not None
        out.append(
            Reminder(
                a.org_id,
                "interview",
                a.company_name,
                (a.interview_at.date() - today).days,
            )
        )
    return out


async def statuses_for_jobs(
    db: AsyncSession, *, org_id: UUID, job_ids: list[UUID]
) -> dict[UUID, str]:
    return await repository.statuses_for_jobs(db, org_id=org_id, job_ids=job_ids)
