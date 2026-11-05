"""One-shot outside effects of a run (claim once, release if refused)."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.agents.flows.models import (
    FlowEffect,
)


async def claim_effect(
    session: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    run_id: UUID,
    node_id: UUID,
    kind: str,
    daily_cap: int,
    global_cap: int | None = None,
    once: bool = True,
) -> str:
    """``"new"`` (go ahead, the row is written), ``"done"`` (this step already did it) or
    ``"capped"`` (a cap was reached). A per-user advisory lock makes count + insert atomic; a cap
    over everyone also takes a short lock of its own, so parallel runs cannot overshoot it.
    ``once=False`` (a repeatable action such as reading a page) only counts: a step that already
    has its row simply runs again."""
    await session.execute(
        select(
            func.pg_advisory_xact_lock(func.hashtextextended(f"effects:{user_id}", 0))
        )
    )
    if (
        await session.execute(
            select(FlowEffect.id).where(
                FlowEffect.run_id == run_id, FlowEffect.node_id == node_id
            )
        )
    ).first():
        return "done" if once else "new"
    today = func.date_trunc("day", func.now())
    used = (
        await session.execute(
            select(func.count(FlowEffect.id)).where(
                FlowEffect.user_id == user_id,
                FlowEffect.kind == kind,
                FlowEffect.created_at >= today,
            )
        )
    ).scalar_one()
    if used >= daily_cap:
        return "capped"
    if (
        global_cap is not None
    ):  # everyone together: a flood of accounts cannot get past this
        await session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"effects:all:{kind}", 0)
                )
            )
        )
        everyone = (
            await session.execute(
                select(func.count(FlowEffect.id)).where(
                    FlowEffect.kind == kind, FlowEffect.created_at >= today
                )
            )
        ).scalar_one()
        if everyone >= global_cap:
            return "capped"
    session.add(
        FlowEffect(
            org_id=org_id, user_id=user_id, run_id=run_id, node_id=node_id, kind=kind
        )
    )
    await session.flush()
    return "new"


async def release_effect(session: AsyncSession, *, run_id: UUID, node_id: UUID) -> None:
    """Give an effect's slot back (the outside call was refused, nothing happened)."""
    await session.execute(
        delete(FlowEffect).where(
            FlowEffect.run_id == run_id, FlowEffect.node_id == node_id
        )
    )
