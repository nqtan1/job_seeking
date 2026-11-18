"""The Assistant inbox (ADR 0042): code that finishes work for a user (a flow run, the daily
reminders) posts a short server-built line here; the coach registers the one sink that stores it in
the user's Assistant conversation. Core imports no module, so ``agents`` and ``identity`` reach
the coach without depending on it.

``post`` runs inside the caller's transaction (the caller commits) under a savepoint: a failing
sink is logged by type and rolled back alone, so it never breaks the caller's own record."""

import logging
from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

Kind = Literal["run_done", "run_failed", "reminder"]
Sink = Callable[..., Awaitable[None]]

_sink: Sink | None = None


def register_sink(fn: Sink) -> None:
    global _sink
    if _sink is not None:
        raise RuntimeError("an inbox sink is already registered")
    _sink = fn


async def post(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    kind: Kind,
    params: dict[str, str | int],
    link: str | None = None,
) -> None:
    """``params`` fill the sink's per-language template of ``kind`` (e.g. name, code, count)."""
    if _sink is None:
        return
    try:
        async with db.begin_nested():
            await _sink(
                db, org_id=org_id, user_id=user_id, kind=kind, params=params, link=link
            )
    except Exception as exc:  # noqa: BLE001  (the inbox is a courtesy: never fail the caller)
        logger.error(
            "inbox post failed", extra={"kind": kind, "error_type": type(exc).__name__}
        )
