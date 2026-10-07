"""``ai_calls`` (ARCHITECTURE.md §4.3, §11.2): one row per LLM call, **metadata only**.

Never store prompt, CV, or letter content here: rows are kept 13 months for usage/cost
dashboards and per-user quotas (ADR 0009, ADR 0014). ``reserve_call``/``finish_call`` are used
by both gateways (``ai/gemini.py``, ``ai/qwen.py``).
"""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.ai.gateway import QuotaExceeded
from recruitai.core.db import Base
from recruitai.core.ids import new_id


class AiCall(Base):
    __tablename__ = "ai_calls"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error')", name="status"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens"),
        CheckConstraint("latency_ms >= 0", name="latency"),
        Index("ix_ai_calls_org_id_created_at", "org_id", "created_at"),
        # The daily quota counts a user's calls since midnight on EVERY model call.
        Index("ix_ai_calls_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Needed for per-user quotas (ADR 0009). Kept (NULL) if the user is deleted: metadata only.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    feature: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


async def count_calls_today(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Used for the daily per-user quota (P1-12). "Today" is UTC midnight, matching
    ``created_at``'s timezone."""
    today = datetime.now(UTC).date()
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    return (
        await session.execute(
            select(func.count(AiCall.id)).where(
                AiCall.user_id == user_id, AiCall.created_at >= today_start
            )
        )
    ).scalar_one()


async def reserve_call(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    feature: str,
    model: str,
    prompt_version: str,
    quota: int,
) -> uuid.UUID:
    """Enforce the daily quota *and* count this call atomically, before the model runs.

    A per-user advisory lock serializes check + insert, so N parallel requests at quota-1
    can't all pass (the old check-then-record let them). The placeholder row starts as
    ``status='error'``: if the process dies mid-call it stays counted, which is the safe side
    for cost. ``finish_call`` fills in the real outcome. Commits, which also releases the lock
    and keeps a transaction from sitting idle during the model call."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(str(user_id), 0)))
    )
    if await count_calls_today(session, user_id=user_id) >= quota:
        await session.rollback()
        raise QuotaExceeded()
    call = AiCall(
        org_id=org_id,
        user_id=user_id,
        feature=feature,
        model=model,
        prompt_version=prompt_version,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        status="error",
    )
    session.add(call)
    await session.flush()
    call_id = call.id
    await session.commit()
    return call_id


async def finish_call(
    session: AsyncSession,
    call_id: uuid.UUID,
    *,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    status: str,
) -> None:
    """Record the outcome (metadata only, never prompt/response content). Commits
    immediately: the call happened whether or not the caller's transaction later rolls back."""
    await session.execute(
        update(AiCall)
        .where(AiCall.id == call_id)
        .values(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            status=status,
        )
    )
    await session.commit()


async def export_rows(session: AsyncSession, *, org_id: uuid.UUID) -> list[AiCall]:
    """The org's usage records (metadata only: tokens, model, latency), for the data export."""
    rows = await session.execute(
        select(AiCall).where(AiCall.org_id == org_id).order_by(AiCall.created_at)
    )
    return list(rows.scalars())


async def delete_older_than(session: AsyncSession, *, cutoff: datetime) -> int:
    """Retention sweep: usage records older than ``cutoff`` (13 months, §11.2)."""
    result = await session.execute(delete(AiCall).where(AiCall.created_at < cutoff))
    return result.rowcount or 0  # type: ignore[attr-defined]  # a DML result always has rowcount


@dataclass
class CallStats:
    """Filled in by the caller inside ``tracked_call``: what the provider reported."""

    input_tokens: int = 0
    output_tokens: int = 0


@asynccontextmanager
async def tracked_call(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    feature: str,
    model: str,
    quota: int,
) -> AsyncIterator[CallStats]:
    """Everything a model call owes the platform, in one place: reserve quota (raises
    ``QuotaExceeded`` before the model is touched), time the call, and record the outcome in
    ``ai_calls``. The status is ``ok`` only if the body ran to the end without raising; an
    exception, a cancellation or a closed stream is recorded as ``error``, and the ``finally``
    runs on all of them. ``feature`` is the versioned id (``cv_extract@2``): the part before
    ``@`` is stored as the groupable feature, the whole as ``prompt_version``."""
    call_id = await reserve_call(
        session,
        org_id=org_id,
        user_id=user_id,
        feature=feature.split("@", 1)[0],
        model=model,
        prompt_version=feature,
        quota=quota,
    )
    stats = CallStats()
    started = time.perf_counter()
    status = "error"
    try:
        yield stats
        status = "ok"
    finally:
        await finish_call(
            session,
            call_id,
            input_tokens=stats.input_tokens,
            output_tokens=stats.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status=status,
        )


async def usage_since(
    session: AsyncSession, *, since: datetime
) -> list[tuple[str, int, int, int, int]]:
    """Platform usage per feature since ``since``: (feature, calls, errors, input, output)
    tokens. Counts only: no prompts, no user content."""
    rows = await session.execute(
        select(
            AiCall.feature,
            func.count(),
            func.count().filter(AiCall.status == "error"),
            func.coalesce(func.sum(AiCall.input_tokens), 0),
            func.coalesce(func.sum(AiCall.output_tokens), 0),
        )
        .where(AiCall.created_at >= since)
        .group_by(AiCall.feature)
        .order_by(AiCall.feature)
    )
    return [(f, int(c), int(e), int(i), int(o)) for f, c, e, i, o in rows.all()]


async def feature_stats(
    session: AsyncSession, *, since: datetime
) -> dict[str, dict[str, object]]:
    """Per feature since ``since``: calls, errors, average and p95 latency, tokens, and the
    prompt version of the most recent call. Counts and timings only, no content."""
    rows = await session.execute(
        select(
            AiCall.feature,
            func.count(),
            func.count().filter(AiCall.status == "error"),
            func.coalesce(func.avg(AiCall.latency_ms), 0),
            func.coalesce(
                func.percentile_cont(0.95).within_group(AiCall.latency_ms), 0
            ),
            func.coalesce(func.sum(AiCall.input_tokens), 0),
            func.coalesce(func.sum(AiCall.output_tokens), 0),
        )
        .where(AiCall.created_at >= since)
        .group_by(AiCall.feature)
    )
    stats: dict[str, dict[str, object]] = {
        feature: {
            "calls": int(calls),
            "errors": int(errors),
            "avg_latency_ms": int(avg),
            "p95_latency_ms": int(p95),
            "input_tokens": int(tin),
            "output_tokens": int(tout),
        }
        for feature, calls, errors, avg, p95, tin, tout in rows.all()
    }
    last = await session.execute(
        select(AiCall.feature, AiCall.prompt_version)
        .where(AiCall.created_at >= since)
        .ext(distinct_on(AiCall.feature))
        .order_by(AiCall.feature, AiCall.created_at.desc())
    )
    for feature, prompt_version in last.all():
        stats[feature]["prompt_version"] = prompt_version
    return stats
