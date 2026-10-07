"""The daily AI quota holds under parallel requests (real connections, no shared session)."""

import asyncio
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.gateway import QuotaExceeded
from recruitai.ai.usage import finish_call, reserve_call
from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import OrgContext, get_org_context
from tests.fixtures.db import purge_tenant


async def test_parallel_reservations_never_exceed_the_quota(db_engine: AsyncEngine):
    async with db_engine.connect() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        ctx = await get_org_context(
            CurrentUser(firebase_uid=f"uid-{uuid4().hex[:8]}", email="q@example.test"),
            session,
            x_org_id=None,
        )
        await session.close()

    async def one_request() -> str:
        async with db_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                call_id = await reserve_call(
                    session,
                    org_id=ctx.org_id,
                    user_id=ctx.user_id,
                    feature="f",
                    model="m",
                    prompt_version="f@1",
                    quota=3,
                )
                await finish_call(
                    session,
                    call_id,
                    input_tokens=1,
                    output_tokens=1,
                    latency_ms=1,
                    status="ok",
                )
                return "ok"
            except QuotaExceeded:
                return "quota"
            finally:
                await session.close()

    try:
        results = await asyncio.gather(*(one_request() for _ in range(8)))
        await _assert_quota_held(db_engine, ctx, results)
    finally:
        await purge_tenant(db_engine, org_id=ctx.org_id, user_id=ctx.user_id)


async def _assert_quota_held(
    db_engine: AsyncEngine, ctx: OrgContext, results: list[str]
) -> None:
    assert results.count("ok") == 3 and results.count("quota") == 5
    async with db_engine.connect() as verify:
        rows = (
            await verify.execute(
                text(
                    "SELECT count(*), min(status), max(status) FROM ai_calls "
                    "WHERE user_id = :u"
                ),
                {"u": ctx.user_id},
            )
        ).one()
    assert tuple(rows) == (
        3,
        "ok",
        "ok",
    )  # rejected requests leave no row; used ones are final
