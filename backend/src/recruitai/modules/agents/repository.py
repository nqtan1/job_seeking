"""All SQL for the agents module. Every query filters by org_id."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.agents.models import Agent, AgentVersion


async def count_agents(
    session: AsyncSession, *, org_id: UUID, include_archived: bool = False
) -> int:
    stmt = select(func.count()).select_from(Agent).where(Agent.org_id == org_id)
    if not include_archived:
        stmt = stmt.where(Agent.archived_at.is_(None))
    return (await session.execute(stmt)).scalar_one()


async def create_agent(
    session: AsyncSession, *, org_id: UUID, values: dict[str, Any]
) -> Agent:
    agent = Agent(org_id=org_id, **values)
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    return agent


async def get_agent(
    session: AsyncSession, *, org_id: UUID, agent_id: UUID
) -> Agent | None:
    return (
        await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        )
    ).scalar_one_or_none()


async def list_agents(session: AsyncSession, *, org_id: UUID) -> list[Agent]:
    return list(
        (
            await session.execute(
                select(Agent)
                .where(Agent.org_id == org_id, Agent.archived_at.is_(None))
                .order_by(Agent.updated_at.desc(), Agent.id)
            )
        ).scalars()
    )


async def add_version(
    session: AsyncSession, *, org_id: UUID, agent_id: UUID, values: dict[str, Any]
) -> AgentVersion:
    version = AgentVersion(org_id=org_id, agent_id=agent_id, **values)
    session.add(version)
    await session.flush()
    await session.refresh(version)
    return version


async def get_version(
    session: AsyncSession, *, org_id: UUID, agent_id: UUID, version: int
) -> AgentVersion | None:
    return (
        await session.execute(
            select(AgentVersion).where(
                AgentVersion.org_id == org_id,
                AgentVersion.agent_id == agent_id,
                AgentVersion.version == version,
            )
        )
    ).scalar_one_or_none()


async def list_versions(
    session: AsyncSession, *, org_id: UUID, agent_id: UUID
) -> list[AgentVersion]:
    return list(
        (
            await session.execute(
                select(AgentVersion)
                .where(AgentVersion.org_id == org_id, AgentVersion.agent_id == agent_id)
                .order_by(AgentVersion.version.desc())
            )
        ).scalars()
    )


async def all_for_org(
    session: AsyncSession, *, org_id: UUID
) -> tuple[list[Agent], list[AgentVersion]]:
    agents = (
        await session.execute(select(Agent).where(Agent.org_id == org_id))
    ).scalars()
    versions = (
        await session.execute(select(AgentVersion).where(AgentVersion.org_id == org_id))
    ).scalars()
    return list(agents), list(versions)


async def versions_by_ids(
    session: AsyncSession, *, org_id: UUID, version_ids: list[UUID]
) -> list[tuple[AgentVersion, Agent]]:
    """Pinned helper versions of this org with their agent. An archived helper still runs the
    flows that pin it (a version is immutable); a missing or foreign one is absent."""
    if not version_ids:
        return []
    rows = await session.execute(
        select(AgentVersion, Agent)
        .join(Agent, Agent.id == AgentVersion.agent_id)
        .where(
            AgentVersion.org_id == org_id,
            Agent.org_id == org_id,
            AgentVersion.id.in_(version_ids),
        )
    )
    return [(v, a) for v, a in rows.all()]
