"""Helpers: identity, immutable versions, trial runs (ADR 0031). Services never import FastAPI."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import LLMGateway
from recruitai.ai.prompts import helper
from recruitai.ai.text import compact_json
from recruitai.core.errors import Conflict, NotFound, ValidationFailed
from recruitai.core.export import rows_as_dicts
from recruitai.core.ids import new_id
from recruitai.modules.agents import versioning
from recruitai.modules.agents.helpers import repository, runner
from recruitai.modules.agents.helpers.models import Agent, AgentVersion
from recruitai.modules.agents.helpers.schemas import (
    AgentCreate,
    AgentPatch,
    Avatar,
    VersionCreate,
    VersionSpec,
)
from recruitai.modules.candidates import service as candidates
from recruitai.modules.jobs import service as jobs
from recruitai.modules.matching import service as matching

MAX_AGENTS_PER_ORG = 20
MAX_AGENTS_EVER = 100  # archived ones count too: archiving is not a way around the cap
PROFILE_CHARS, JOB_CHARS, FIT_CHARS = 6_000, 10_000, 4_000
_IDENTITY_KEYS = ("personal_info", "references")


def default_avatar(agent_id: UUID) -> Avatar:
    """Unique and stable per agent: parts picked from the random tail of its UUID."""
    b = agent_id.bytes
    return Avatar(
        seed=agent_id,
        body=b[10] % 8,
        palette=b[11] % 12,
        eyes=b[12] % 6,
        accessory=b[13] % 8,
    )


def spec_of(version: AgentVersion) -> VersionSpec:
    return VersionSpec.model_validate(
        {
            "role": version.role,
            "instructions": version.instructions,
            "model_tier": version.model_tier,
            "inputs": version.inputs,
            "context_sources": version.context_sources,
            "output": version.output_spec,
        }
    )


def _values(spec: VersionSpec, note: str, version: int) -> dict[str, Any]:
    dumped = spec.model_dump(mode="json")
    return {
        "version": version,
        "role": dumped["role"],
        "instructions": dumped["instructions"],
        "model_tier": dumped["model_tier"],
        "inputs": dumped["inputs"],
        "context_sources": dumped["context_sources"],
        "output_spec": dumped["output"],
        "note": note,
    }


async def create_agent(
    db: AsyncSession, *, org_id: UUID, data: AgentCreate
) -> tuple[Agent, AgentVersion]:
    if await repository.count_agents(db, org_id=org_id) >= MAX_AGENTS_PER_ORG:
        raise ValidationFailed(f"You can have at most {MAX_AGENTS_PER_ORG} helpers.")
    if (
        await repository.count_agents(db, org_id=org_id, include_archived=True)
        >= MAX_AGENTS_EVER
    ):
        raise ValidationFailed("You have reached the limit of helpers you can create.")
    agent_id = new_id()
    agent = await repository.create_agent(
        db,
        org_id=org_id,
        values={
            "id": agent_id,
            "name": data.name.strip(),
            "description": data.description.strip(),
            "avatar": (data.avatar or default_avatar(agent_id)).model_dump(mode="json"),
            "current_version": 1,
        },
    )
    version = await repository.add_version(
        db, org_id=org_id, agent_id=agent.id, values=_values(data.spec, data.note, 1)
    )
    await db.commit()
    return agent, version


async def get_agent(db: AsyncSession, *, org_id: UUID, agent_id: UUID) -> Agent:
    agent = await repository.get_agent(db, org_id=org_id, agent_id=agent_id)
    if agent is None:
        raise NotFound("Helper not found.")
    return agent


async def get_detail(
    db: AsyncSession, *, org_id: UUID, agent_id: UUID
) -> tuple[Agent, AgentVersion]:
    agent = await get_agent(db, org_id=org_id, agent_id=agent_id)
    return agent, await get_version(
        db, org_id=org_id, agent_id=agent_id, version=agent.current_version
    )


async def get_version(
    db: AsyncSession, *, org_id: UUID, agent_id: UUID, version: int
) -> AgentVersion:
    row = await repository.get_version(
        db, org_id=org_id, agent_id=agent_id, version=version
    )
    if row is None:
        raise NotFound("Version not found.")
    return row


async def list_agents(db: AsyncSession, *, org_id: UUID) -> list[Agent]:
    return await repository.list_agents(db, org_id=org_id)


async def list_versions(
    db: AsyncSession, *, org_id: UUID, agent_id: UUID
) -> list[AgentVersion]:
    await get_agent(db, org_id=org_id, agent_id=agent_id)
    return await repository.list_versions(db, org_id=org_id, agent_id=agent_id)


async def patch_agent(
    db: AsyncSession, *, org_id: UUID, agent_id: UUID, data: AgentPatch
) -> Agent:
    agent = await get_agent(db, org_id=org_id, agent_id=agent_id)
    if agent.archived_at is not None:
        raise Conflict("This helper is archived.")
    values: dict[str, Any] = {}
    if data.name is not None:
        values["name"] = data.name.strip()
    if data.description is not None:
        values["description"] = data.description.strip()
    if data.avatar is not None:
        values["avatar"] = data.avatar.model_dump(mode="json")
    if values:
        await versioning.update_row(
            db, Agent, org_id=org_id, id=agent_id, values=values
        )
        await db.commit()
        await db.refresh(agent)
    return agent


async def add_version(
    db: AsyncSession, *, org_id: UUID, agent_id: UUID, data: VersionCreate
) -> AgentVersion:
    agent = await get_agent(db, org_id=org_id, agent_id=agent_id)
    number = await versioning.claim_next_version(
        db, Agent, agent, org_id=org_id, based_on=data.based_on, noun="helper"
    )
    version = await repository.add_version(
        db,
        org_id=org_id,
        agent_id=agent_id,
        values=_values(data.spec, data.note, number),
    )
    await db.commit()
    return version


async def archive(db: AsyncSession, *, org_id: UUID, agent_id: UUID) -> None:
    await get_agent(db, org_id=org_id, agent_id=agent_id)
    await versioning.archive_row(db, Agent, org_id=org_id, id=agent_id)
    await db.commit()


async def context_for(
    db: AsyncSession,
    *,
    org_id: UUID,
    spec: VersionSpec,
    job_id: UUID | None,
    llm: LLMGateway | None = None,
) -> dict[str, str]:
    """The attached sources as text. Contact details and references never go in (ADR 0031).
    With ``llm`` (a test run), a job that has no fit analysis yet gets one first, so a helper that
    reads it can be tried at once; in a flow a "Check my fit" step provides it instead."""
    out: dict[str, str] = {}
    needs_job = "job" in spec.context_sources or "fit" in spec.context_sources
    if needs_job and job_id is None:
        raise ValidationFailed("This helper needs a job: pick one.")
    if "profile" in spec.context_sources:
        profile = await candidates.require_profile(db, org_id=org_id)
        data = {k: v for k, v in profile.data.items() if k not in _IDENTITY_KEYS}
        out["profile"] = compact_json(data)[:PROFILE_CHARS]
    if needs_job and job_id is not None:
        job = await jobs.get_job(db, org_id=org_id, job_id=job_id)  # 404 across orgs
        if "job" in spec.context_sources:
            out["job"] = compact_json(job.data)[:JOB_CHARS]
        if "fit" in spec.context_sources:
            reports = await matching.list_analyses(
                db, org_id=org_id, job_id=job.id, limit=1
            )
            if not reports and llm is not None:
                reports = [
                    await matching.latest_or_analyze(
                        db, llm, org_id=org_id, job_id=job.id
                    )
                ]
            if not reports:
                raise ValidationFailed(
                    "This helper needs a fit analysis: add a “Check my fit” step before it."
                )
            out["fit"] = compact_json(reports[0].data)[:FIT_CHARS]
    return out


async def try_it(
    db: AsyncSession,
    llm: LLMGateway,
    *,
    org_id: UUID,
    agent_id: UUID,
    spec: VersionSpec,
    inputs: dict[str, str],
    job_id: UUID | None,
) -> runner.Outcome:
    """Runs a draft spec once. Quota and ``ai_calls`` are handled by the tenant-bound gateway;
    nothing is stored."""
    agent = await get_agent(db, org_id=org_id, agent_id=agent_id)
    if agent.archived_at is not None:
        raise Conflict("This helper is archived.")
    runner.check_inputs(spec, inputs)  # before any context load or model call
    context = await context_for(db, org_id=org_id, spec=spec, job_id=job_id, llm=llm)
    await db.rollback()  # no transaction held open across the model call
    return await runner.run(
        llm,
        spec,
        values=inputs,
        context=context,
        feature=helper.feature(
            agent_id, "draft"
        ),  # not `agent`: expired by the rollback
    )


async def export_data(
    db: AsyncSession, *, org_id: UUID
) -> dict[str, list[dict[str, object]]]:
    agents, versions = await repository.all_for_org(db, org_id=org_id)
    return {
        "agents": rows_as_dicts(agents),
        "agent_versions": rows_as_dicts(versions),
    }
