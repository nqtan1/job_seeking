"""Parallel edits of one letter all land, with distinct version numbers (row lock)."""

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.letters import PROMPT_VERSION
from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.candidates.schemas import CVInformation, PersonalInfo, RawSkill
from recruitai.modules.jobs import repository as jobs_repo
from recruitai.modules.letters import service
from tests.fixtures.db import purge_tenant
from tests.integration.test_letters_service import DRAFT
from tests.unit.test_jobs_parser import blank_job


async def test_parallel_block_edits_get_distinct_consecutive_versions(
    db_engine: AsyncEngine,
):
    async with db_engine.connect() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        ctx = await get_org_context(
            CurrentUser(firebase_uid=f"uid-{uuid4().hex[:8]}", email="e@example.test"),
            session,
            x_org_id=None,
        )
        await candidates_repo.upsert(
            session,
            org_id=ctx.org_id,
            document_id=None,
            info=CVInformation(
                personal_info=PersonalInfo(name="Ada"),
                formations=[],
                experiences=[],
                skills=[RawSkill(name="Python")],
            ),
        )
        job = await jobs_repo.add(
            session,
            org_id=ctx.org_id,
            source="manual",
            external_id=None,
            info=blank_job(),
        )
        llm = FakeLLMGateway()
        llm.queue(PROMPT_VERSION, DRAFT)
        letter = await service.generate(session, llm, org_id=ctx.org_id, job_id=job.id)
        await session.close()

    async def edit(i: int) -> None:
        async with db_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                await service.edit_block(
                    session,
                    org_id=ctx.org_id,
                    letter_id=letter.id,
                    block="body",
                    text=f"paragraph {i}",
                    index=i % 3,
                )
            finally:
                await session.close()

    try:
        await asyncio.gather(*(edit(i) for i in range(6)))
        async with db_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            versions = await service.list_versions(
                session, org_id=ctx.org_id, letter_id=letter.id
            )
            await session.close()
        assert sorted(v.n for v in versions) == list(
            range(1, 8)
        )  # 1 + six edits, no gaps
    finally:
        await purge_tenant(db_engine, org_id=ctx.org_id, user_id=ctx.user_id)
