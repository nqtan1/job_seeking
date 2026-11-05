"""Flows and their versions."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.agents.flows.models import (
    Flow,
    FlowVersion,
)


async def count_flows(
    session: AsyncSession, *, org_id: UUID, include_archived: bool = False
) -> int:
    stmt = select(func.count()).select_from(Flow).where(Flow.org_id == org_id)
    if not include_archived:
        stmt = stmt.where(Flow.archived_at.is_(None))
    return (await session.execute(stmt)).scalar_one()


async def create_flow(
    session: AsyncSession, *, org_id: UUID, values: dict[str, Any]
) -> Flow:
    flow = Flow(org_id=org_id, **values)
    session.add(flow)
    await session.flush()
    await session.refresh(flow)
    return flow


async def get_flow(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> Flow | None:
    return (
        await session.execute(
            select(Flow).where(Flow.id == flow_id, Flow.org_id == org_id)
        )
    ).scalar_one_or_none()


async def list_flows(session: AsyncSession, *, org_id: UUID) -> list[Flow]:
    return list(
        (
            await session.execute(
                select(Flow)
                .where(Flow.org_id == org_id, Flow.archived_at.is_(None))
                .order_by(Flow.updated_at.desc(), Flow.id)
            )
        ).scalars()
    )


async def add_flow_version(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID, values: dict[str, Any]
) -> FlowVersion:
    row = FlowVersion(org_id=org_id, flow_id=flow_id, **values)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_flow_version(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID, version: int
) -> FlowVersion | None:
    return (
        await session.execute(
            select(FlowVersion).where(
                FlowVersion.org_id == org_id,
                FlowVersion.flow_id == flow_id,
                FlowVersion.version == version,
            )
        )
    ).scalar_one_or_none()


async def get_flow_version_by_id(
    session: AsyncSession, *, org_id: UUID, version_id: UUID
) -> FlowVersion | None:
    return (
        await session.execute(
            select(FlowVersion).where(
                FlowVersion.org_id == org_id, FlowVersion.id == version_id
            )
        )
    ).scalar_one_or_none()


async def list_flow_versions(
    session: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> list[FlowVersion]:
    return list(
        (
            await session.execute(
                select(FlowVersion)
                .where(FlowVersion.org_id == org_id, FlowVersion.flow_id == flow_id)
                .order_by(FlowVersion.version.desc())
            )
        ).scalars()
    )
