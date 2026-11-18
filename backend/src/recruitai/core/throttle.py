"""The windows behind every rate limit. ``hit_shared`` (authenticated, per user) counts in the
``rate_hits`` table, so the limit holds at any number of API instances (ADR 0041); ``hit`` is a
sliding window in memory per instance, for the unauthenticated global limit and for processes
without a database engine (unit tests). The DB-backed daily AI quotas (``ai/usage.py``) stay
the real cost control. No imports from ``auth``: the auth dependency itself calls it."""

import time
from collections import defaultdict, deque
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.config import get_settings
from recruitai.core import db
from recruitai.core.db import Base, rows_affected

_MAX_KEYS = 10_000
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


class RateHit(Base):
    __tablename__ = "rate_hits"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False)


def hit(name: str, key: str, *, limit: int, per_s: float = 60.0) -> int | None:
    """Count one request. Returns ``None`` if allowed, else the seconds to wait."""
    now = time.monotonic()
    if len(_hits) > _MAX_KEYS:  # drop idle keys so the dict cannot grow forever
        for k in [k for k, q in _hits.items() if not q or q[-1] <= now - per_s]:
            del _hits[k]
    window = _hits[(name, key)]
    while window and window[0] <= now - per_s:
        window.popleft()
    if len(window) >= limit:
        return max(1, int(window[0] + per_s - now) + 1)
    window.append(now)
    return None


# Fixed window on the DB clock, one atomic upsert: concurrent requests never lose a count.
_UPSERT = text(
    "INSERT INTO rate_hits (key, window_start, count) VALUES (:key,"
    " to_timestamp(floor(extract(epoch FROM clock_timestamp()) / :per) * :per), 1)"
    " ON CONFLICT (key, window_start) DO UPDATE SET count = rate_hits.count + 1"
    " RETURNING count,"
    " ceil(extract(epoch FROM window_start) + :per - extract(epoch FROM clock_timestamp()))"
)


async def hit_shared(
    name: str, key: str, *, limit: int, per_s: float = 60.0
) -> int | None:
    """Like ``hit``, counted in Postgres in its own short transaction (never the request's,
    which may roll back). Over the limit the count still grows; harmless, the window ends."""
    engine = db._engine
    if (
        engine is None
    ):  # no database in this process: unit tests only, never a deployed app
        if get_settings().env != "local":
            raise RuntimeError("shared rate limit without a database engine")
        return hit(name, key, limit=limit, per_s=per_s)
    # over the limit on this instance already: answer without a DB write (a flood costs no upserts)
    if (local := hit(name, key, limit=limit, per_s=per_s)) is not None:
        return local
    async with engine.begin() as conn:
        row = (
            await conn.execute(_UPSERT, {"key": f"{name}:{key}", "per": per_s})
        ).one()
    return None if row[0] <= limit else max(1, int(row[1]))


async def sweep(session: AsyncSession, *, cutoff: datetime) -> int:
    """Delete windows that started before ``cutoff`` (the caller commits)."""
    return rows_affected(
        await session.execute(delete(RateHit).where(RateHit.window_start < cutoff))
    )
