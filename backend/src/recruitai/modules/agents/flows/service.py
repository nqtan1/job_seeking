"""Flows: CRUD with immutable versions, validation, and the data export (ADR 0031). Starting,
resuming and cancelling runs lives in ``runs.py``."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import Conflict, NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.modules.agents import versioning
from recruitai.modules.agents.blocks.catalogue import BLOCKS
from recruitai.modules.agents.connections import repository as connections_repo
from recruitai.modules.agents.contacts import repository as recipients_repo
from recruitai.modules.agents.flows import engine
from recruitai.modules.agents.flows import graph as g
from recruitai.modules.agents.flows import repository as repo
from recruitai.modules.agents.flows.models import (
    Flow,
    FlowVersion,
)
from recruitai.modules.agents.flows.schemas import FlowCreate, FlowVersionCreate

MAX_FLOWS_PER_ORG = 20
MAX_FLOWS_EVER = 100  # archived ones count too: archiving is not a way around the cap


# Saving is allowed with open problems (work in progress); these make a graph unreadable.
UNSAVABLE = {"duplicate_node_id", "duplicate_edge_id"}


def graph_of(version: FlowVersion) -> g.Graph:
    return g.Graph.model_validate(version.graph)


def ai_calls(graph: g.Graph) -> int:
    """Model calls a run can make: one per helper, plus what each block says it uses."""
    return sum(
        1
        if isinstance(n, g.AgentNode)
        else BLOCKS[n.tool].ai_uses
        if isinstance(n, g.ToolNode)
        else 0
        for n in graph.nodes
    )


async def check(
    db: AsyncSession,
    *,
    org_id: UUID,
    graph: g.Graph,
    agents: dict[UUID, g.AgentInfo] | None = None,
    flow_id: UUID | None = None,
) -> list[g.Issue]:
    if agents is None:
        agents = await engine.load_agents(db, org_id=org_id, graph=graph)
    issues = g.validate(graph, agents)
    for n in graph.nodes:
        if isinstance(n, g.ToolNode) and BLOCKS[n.tool].starts_runs:
            issues += await _target_issues(db, org_id, flow_id, n)
    return issues


async def _target_issues(
    db: AsyncSession, org_id: UUID, own_id: UUID | None, node: g.ToolNode
) -> list[g.Issue]:
    """A for_each may start another live automation of this account that does not fan out itself
    (one level only: no loops, no explosion)."""
    if node.flow_id is None:
        return [g.Issue("target_missing", "Choose the flow to start.", node.id)]
    if node.flow_id == own_id:
        return [g.Issue("target_self", "A flow cannot start itself.", node.id)]
    gone = [g.Issue("target_unavailable", "The flow to start is missing.", node.id)]
    try:
        flow, version = await get_detail(db, org_id=org_id, flow_id=node.flow_id)
    except NotFound:
        return gone
    if flow.archived_at is not None:
        return gone
    target = graph_of(version)
    if any(
        isinstance(n, g.ToolNode) and BLOCKS[n.tool].starts_runs for n in target.nodes
    ):
        return [g.Issue("target_nested", "That flow starts flows itself.", node.id)]
    return []


def _refuse_unsavable(issues: list[g.Issue]) -> None:
    if bad := [i for i in issues if i.code in UNSAVABLE]:
        raise ValidationFailed(bad[0].message)


async def create_flow(
    db: AsyncSession, *, org_id: UUID, data: FlowCreate
) -> tuple[Flow, FlowVersion]:
    if await repo.count_flows(db, org_id=org_id) >= MAX_FLOWS_PER_ORG:
        raise ValidationFailed(f"You can have at most {MAX_FLOWS_PER_ORG} flows.")
    if (
        await repo.count_flows(db, org_id=org_id, include_archived=True)
        >= MAX_FLOWS_EVER
    ):
        raise ValidationFailed("You have reached the limit of flows you can create.")
    _refuse_unsavable(await check(db, org_id=org_id, graph=data.graph))
    flow = await repo.create_flow(
        db,
        org_id=org_id,
        values={
            "name": data.name.strip(),
            "description": data.description.strip(),
            "current_version": 1,
        },
    )
    version = await repo.add_flow_version(
        db,
        org_id=org_id,
        flow_id=flow.id,
        values=_version_values(data.graph, data.note, 1),
    )
    await db.commit()
    return flow, version


def _version_values(graph: g.Graph, note: str, version: int) -> dict[str, Any]:
    return {
        "version": version,
        "graph": graph.model_dump(mode="json", by_alias=True),
        "schema_version": g.SCHEMA_VERSION,
        "note": note,
    }


async def get_flow(db: AsyncSession, *, org_id: UUID, flow_id: UUID) -> Flow:
    flow = await repo.get_flow(db, org_id=org_id, flow_id=flow_id)
    if flow is None:
        raise NotFound("Flow not found.")
    return flow


async def get_detail(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> tuple[Flow, FlowVersion]:
    flow = await get_flow(db, org_id=org_id, flow_id=flow_id)
    version = await repo.get_flow_version(
        db, org_id=org_id, flow_id=flow_id, version=flow.current_version
    )
    if version is None:
        raise NotFound("Flow not found.")
    return flow, version


async def list_flows(db: AsyncSession, *, org_id: UUID) -> list[Flow]:
    return await repo.list_flows(db, org_id=org_id)


async def list_with_versions(
    db: AsyncSession, *, org_id: UUID
) -> tuple[list[Flow], dict[UUID, FlowVersion]]:
    return (
        await repo.list_flows(db, org_id=org_id),
        await repo.current_versions(db, org_id=org_id),
    )


async def list_versions(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID
) -> list[FlowVersion]:
    await get_flow(db, org_id=org_id, flow_id=flow_id)
    return await repo.list_flow_versions(db, org_id=org_id, flow_id=flow_id)


async def patch_flow(
    db: AsyncSession,
    *,
    org_id: UUID,
    flow_id: UUID,
    name: str | None,
    description: str | None,
) -> Flow:
    flow = await get_flow(db, org_id=org_id, flow_id=flow_id)
    if flow.archived_at is not None:
        raise Conflict("This flow is archived.")
    values: dict[str, Any] = {}
    if name is not None:
        if not name.strip():
            raise ValidationFailed("The name is empty.")
        values["name"] = name.strip()
    if description is not None:
        values["description"] = description.strip()
    if values:
        await versioning.update_row(db, Flow, org_id=org_id, id=flow_id, values=values)
        await db.commit()
        await db.refresh(flow)
    return flow


async def add_version(
    db: AsyncSession, *, org_id: UUID, flow_id: UUID, data: FlowVersionCreate
) -> FlowVersion:
    flow = await get_flow(db, org_id=org_id, flow_id=flow_id)
    _refuse_unsavable(await check(db, org_id=org_id, graph=data.graph, flow_id=flow_id))
    number = await versioning.claim_next_version(
        db, Flow, flow, org_id=org_id, based_on=data.based_on, noun="flow"
    )
    version = await repo.add_flow_version(
        db,
        org_id=org_id,
        flow_id=flow_id,
        values=_version_values(data.graph, data.note, number),
    )
    await db.commit()
    return version


async def archive(db: AsyncSession, *, org_id: UUID, flow_id: UUID) -> None:
    await get_flow(db, org_id=org_id, flow_id=flow_id)
    await versioning.archive_row(db, Flow, org_id=org_id, id=flow_id)
    await db.commit()


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, object]]]:
    flows, versions, runs, steps, handoffs = await repo.all_for_org(db, org_id=org_id)
    return {
        "flows": rows_as_dicts(flows),
        "flow_versions": rows_as_dicts(versions),
        "flow_runs": rows_as_dicts(runs),
        "flow_run_steps": rows_as_dicts(steps),
        "flow_run_handoffs": rows_as_dicts(handoffs),
        "flow_schedules": rows_as_dicts(
            await repo.schedules_for_org(db, org_id=org_id)
        ),
        # the link secrets are not data about the person: never in the export
        "email_recipients": [
            {
                k: v
                for k, v in row.items()
                if k not in ("confirm_hash", "unsubscribe_token")
            }
            for row in rows_as_dicts(
                await recipients_repo.all_for_org(db, org_id=org_id)
            )
        ],
        # who the person linked, not how: no link code
        "connections": [
            {k: v for k, v in row.items() if k not in ("link_hash", "link_expires_at")}
            for row in rows_as_dicts(
                await connections_repo.all_for_org(db, org_id=org_id)
            )
        ],
    }
