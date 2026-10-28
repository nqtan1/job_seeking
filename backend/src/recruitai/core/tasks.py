"""Procrastinate app + the transactional-enqueue helper (ADR 0017).

Enqueue only through ``enqueue()``: it defers on the caller's session connection so the business
write and the job commit or roll back together. Status reads go through ``task_runs``, never
Procrastinate's tables. Its schema is not managed by Alembic (apply with its own CLI).
"""

import asyncio
import logging
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Any

import procrastinate
import psycopg
from procrastinate import PsycopgConnector
from procrastinate.tasks import Task
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from recruitai.config import Settings, get_settings
from recruitai.core.db import Base, database_url, iam_password
from recruitai.core.ids import new_id

logger = logging.getLogger(__name__)


class TaskRun(Base):
    __tablename__ = "task_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'done', 'failed')", name="status"),
        Index("ix_task_runs_org_id_created_at", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="queued"
    )
    error_code: Mapped[str | None] = mapped_column(String)
    result_ref: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class _IamConnection(psycopg.AsyncConnection):
    """Pool connection class: logs in with a fresh Cloud SQL IAM token (ADR 0028)."""

    @classmethod
    async def connect(cls, conninfo: str = "", **kwargs: Any) -> Any:
        kwargs["password"] = await asyncio.to_thread(iam_password)
        return await super().connect(conninfo, **kwargs)


def build_app(settings: Settings) -> procrastinate.App:
    """Procrastinate's connector wants a plain psycopg DSN, not the SQLAlchemy URL form."""
    conninfo = database_url(settings).set(drivername="postgresql")
    extra: dict[str, Any] = (
        {"connection_class": _IamConnection} if settings.db_iam_auth else {}
    )
    return procrastinate.App(
        connector=PsycopgConnector(
            conninfo=conninfo.render_as_string(hide_password=False), **extra
        )
    )


@lru_cache
def _api_app() -> procrastinate.App:
    """A Procrastinate app with no tasks registered, for API processes that only *enqueue*
    by task name (``configure_task`` accepts unknown names). It never opens a pool: the job is
    inserted on the caller's own connection. This is what keeps API code from importing
    ``recruitai.worker`` (a second DB engine, storage client and every task's imports)."""
    return build_app(get_settings())


async def enqueue(
    session: AsyncSession,
    *,
    task: Task | str,  # type: ignore[type-arg]
    org_id: uuid.UUID,
    kind: str,
    task_kwargs: dict[str, Any] | None = None,
) -> uuid.UUID:
    """The only correct way to enqueue a task. Writes the ``task_runs`` row and defers the
    job on the same raw connection as the caller's session — both commit or roll back
    together. The caller still owns the transaction: this does not call ``session.commit()``.
    """
    task_run_id = new_id()
    session.add(TaskRun(id=task_run_id, org_id=org_id, kind=kind))
    await session.flush()

    conn = await session.connection()
    raw = (await conn.get_raw_connection()).driver_connection
    deferrer = (
        _api_app().configure_task(task, connection=raw)
        if isinstance(task, str)
        else task.configure(connection=raw)
    )
    await deferrer.defer_async(task_run_id=str(task_run_id), **(task_kwargs or {}))
    return task_run_id


async def mark_done(
    session: AsyncSession, task_run_id: uuid.UUID, *, result_ref: str | None = None
) -> None:
    await session.execute(
        update(TaskRun)
        .where(TaskRun.id == task_run_id)
        .values(status="done", result_ref=result_ref)
    )
    await session.commit()


async def mark_failed(
    session: AsyncSession, task_run_id: uuid.UUID, *, error_code: str
) -> None:
    logger.error(
        "task_failed", extra={"error_code": error_code}
    )  # alert: infra/monitoring.tf
    await session.execute(
        update(TaskRun)
        .where(TaskRun.id == task_run_id)
        .values(status="failed", error_code=error_code)
    )
    await session.commit()


async def find_queued(
    session: AsyncSession, *, org_id: uuid.UUID, kind: str
) -> uuid.UUID | None:
    """The org's still-queued task of ``kind``, if any: lets a request that must not pile up
    (a data export) return the pending task instead of enqueueing a second one."""
    return await session.scalar(
        select(TaskRun.id)
        .where(
            TaskRun.org_id == org_id, TaskRun.kind == kind, TaskRun.status == "queued"
        )
        .order_by(TaskRun.created_at)
        .limit(1)
    )
