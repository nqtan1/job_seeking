"""Two simultaneous PATCHes of different sections both survive (row lock, real connections)."""

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.candidates import repository, service
from recruitai.modules.candidates.schemas import (
    CVInformation,
    PersonalInfo,
    ProfileUpdate,
    RawSkill,
)
from tests.fixtures.db import purge_tenant


async def test_concurrent_patches_of_different_sections_are_both_kept(
    db_engine: AsyncEngine,
):
    async with db_engine.connect() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        ctx = await get_org_context(
            CurrentUser(firebase_uid=f"uid-{uuid4().hex[:8]}", email="p@example.test"),
            session,
            x_org_id=None,
        )
        await repository.upsert(
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
        await session.commit()
        await session.close()

    async def patch(changes: ProfileUpdate) -> None:
        async with db_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                await service.update_profile(
                    session, org_id=ctx.org_id, changes=changes
                )
            finally:
                await session.close()

    try:
        await asyncio.gather(
            *(
                [patch(ProfileUpdate(summary=f"s{i}")) for i in range(3)]
                + [patch(ProfileUpdate(skills=[RawSkill(name="Rust")]))]
            )
        )

        async with db_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            profile = await repository.get(session, org_id=ctx.org_id)
            await session.close()
        assert profile is not None
        assert profile.data["skills"] == [{"name": "Rust", "category": None}]
        assert profile.data["summary"] in {
            "s0",
            "s1",
            "s2",
        }  # a summary patch was not lost either
    finally:
        await purge_tenant(db_engine, org_id=ctx.org_id, user_id=ctx.user_id)
