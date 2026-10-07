"""All SQL for the applications module. Every query filters by org_id."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
)


async def get(
    session: AsyncSession,
    *,
    org_id: UUID,
    application_id: UUID,
    for_update: bool = False,
) -> Application | None:
    """``for_update`` locks the row: a status change reads the current status, validates the
    move against it and writes, so two simultaneous changes must not both pass."""
    stmt = select(Application).where(
        Application.org_id == org_id, Application.id == application_id
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_org(
    session: AsyncSession,
    *,
    org_id: UUID,
    status: str | None,
    limit: int,
    offset: int,
) -> list[Application]:
    stmt = select(Application).where(Application.org_id == org_id)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    rows = await session.execute(
        stmt.order_by(Application.created_at.desc(), Application.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.scalars())


async def add_event(
    session: AsyncSession,
    *,
    application: Application,
    from_status: str | None,
    to_status: str,
    note: str | None,
) -> ApplicationEvent:
    event = ApplicationEvent(
        application_id=application.id,
        org_id=application.org_id,
        from_status=from_status,
        to_status=to_status,
        at=datetime.now(UTC),
        note=note,
    )
    session.add(event)
    await session.flush()
    return event


async def create(
    session: AsyncSession,
    *,
    org_id: UUID,
    job_id: UUID | None,
    company_name: str,
    job_title: str | None,
    source: str,
    status: str,
    applied_at: date | None,
    notes: str | None,
) -> Application:
    """The application and its creation event ("nothing" → first status)."""
    application = Application(
        org_id=org_id,
        job_id=job_id,
        company_name=company_name,
        job_title=job_title,
        source=source,
        status=status,
        applied_at=applied_at,
        notes=notes,
    )
    session.add(application)
    await session.flush()
    await add_event(
        session, application=application, from_status=None, to_status=status, note=None
    )
    await session.refresh(application)  # server-side created_at / updated_at
    return application


async def update(
    session: AsyncSession, application: Application, changes: dict[str, Any]
) -> Application:
    for field, value in changes.items():
        setattr(application, field, value)
    await session.flush()
    await session.refresh(application)
    return application


async def list_events(
    session: AsyncSession, *, org_id: UUID, application_id: UUID
) -> list[ApplicationEvent]:
    rows = await session.execute(
        select(ApplicationEvent)
        .where(
            ApplicationEvent.org_id == org_id,
            ApplicationEvent.application_id == application_id,
        )
        .order_by(ApplicationEvent.at, ApplicationEvent.id)
    )
    return list(rows.scalars())


async def delete(session: AsyncSession, application: Application) -> None:
    await session.delete(application)  # events go with it (ON DELETE CASCADE)
    await session.flush()


async def all_for_org(session: AsyncSession, *, org_id: UUID) -> list[Application]:
    rows = await session.execute(
        select(Application)
        .where(Application.org_id == org_id)
        .order_by(Application.created_at)
    )
    return list(rows.scalars())


async def all_events_for_org(
    session: AsyncSession, *, org_id: UUID
) -> list[ApplicationEvent]:
    rows = await session.execute(
        select(ApplicationEvent)
        .where(ApplicationEvent.org_id == org_id)
        .order_by(ApplicationEvent.at, ApplicationEvent.id)
    )
    return list(rows.scalars())


async def attach_document(
    session: AsyncSession, *, org_id: UUID, application_id: UUID, document_id: UUID
) -> None:
    """Idempotent: attaching the same file twice is a no-op."""
    await session.execute(
        pg_insert(ApplicationDocument)
        .values(org_id=org_id, application_id=application_id, document_id=document_id)
        .on_conflict_do_nothing()
    )


async def detach_document(
    session: AsyncSession, *, org_id: UUID, application_id: UUID, document_id: UUID
) -> None:
    await session.execute(
        sql_delete(ApplicationDocument).where(
            ApplicationDocument.org_id == org_id,
            ApplicationDocument.application_id == application_id,
            ApplicationDocument.document_id == document_id,
        )
    )


async def document_attached(
    session: AsyncSession, *, org_id: UUID, document_id: UUID
) -> bool:
    row = await session.execute(
        select(ApplicationDocument.document_id)
        .where(
            ApplicationDocument.org_id == org_id,
            ApplicationDocument.document_id == document_id,
        )
        .limit(1)
    )
    return row.first() is not None


async def list_documents(
    session: AsyncSession, *, org_id: UUID, application_id: UUID
) -> list[ApplicationDocument]:
    rows = await session.execute(
        select(ApplicationDocument)
        .where(
            ApplicationDocument.org_id == org_id,
            ApplicationDocument.application_id == application_id,
        )
        .order_by(ApplicationDocument.created_at)
    )
    return list(rows.scalars())


async def all_documents_for_org(
    session: AsyncSession, *, org_id: UUID
) -> list[ApplicationDocument]:
    rows = await session.execute(
        select(ApplicationDocument).where(ApplicationDocument.org_id == org_id)
    )
    return list(rows.scalars())


async def due_for_followup(
    session: AsyncSession, *, sent_on: date
) -> list[Application]:
    """Applications still at "applied" that were sent exactly ``sent_on`` (every org)."""
    rows = await session.execute(
        select(Application).where(
            Application.status == "applied",
            func.coalesce(Application.applied_at, func.date(Application.updated_at))
            == sent_on,
        )
    )
    return list(rows.scalars())


async def interviews_on(
    session: AsyncSession, *, days: list[date]
) -> list[Application]:
    rows = await session.execute(
        select(Application).where(
            Application.status != "rejected",
            func.date(Application.interview_at).in_(days),
        )
    )
    return list(rows.scalars())


async def statuses_for_jobs(
    session: AsyncSession, *, org_id: UUID, job_ids: list[UUID]
) -> dict[UUID, str]:
    """``{job id: status}`` of the org's applications linked to these jobs."""
    if not job_ids:
        return {}
    rows = await session.execute(
        select(Application.job_id, Application.status).where(
            Application.org_id == org_id, Application.job_id.in_(job_ids)
        )
    )
    return {job_id: status for job_id, status in rows.all() if job_id is not None}
