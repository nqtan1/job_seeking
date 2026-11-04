"""Abuse limits: a script hammering the API, a huge body, and many accounts spending together."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.gateway import QuotaExceeded
from recruitai.ai.usage import count_calls_today, reserve_call
from recruitai.config import get_settings
from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from tests.fixtures.db import purge_tenant


async def test_a_hammering_script_is_slowed_and_every_answer_carries_the_security_headers(
    client, ada, monkeypatch
):
    monkeypatch.setattr(get_settings(), "api_rate_limit_per_min", 5)
    for _ in range(5):
        ok = await client.get("/api/v1/me", headers=ada)
        assert ok.status_code == 200
    slow = await client.get("/api/v1/me", headers=ada)
    assert slow.status_code == 429 and int(slow.headers["Retry-After"]) >= 1
    for r in (ok, slow):
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Cache-Control"] == "no-store"


async def test_a_body_over_the_cap_is_refused_before_it_is_read(client, ada):
    big = await client.post(
        "/api/v1/agents", headers=ada, content=b"x" * (13 * 1024 * 1024)
    )
    assert big.status_code == 413 and big.json()["code"] == "payload_too_large"


async def test_the_global_daily_cap_stops_many_accounts_but_not_a_turn_in_progress(
    db_engine: AsyncEngine, monkeypatch
):
    async with db_engine.connect() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        ctx = await get_org_context(
            CurrentUser(firebase_uid=f"uid-{uuid4().hex[:8]}", email="g@example.test"),
            session,
            x_org_id=None,
        )
        so_far = await count_calls_today(session)
        monkeypatch.setattr(get_settings(), "ai_daily_quota_global", so_far + 1)

        async def call(quota: int) -> None:
            await reserve_call(
                session,
                org_id=ctx.org_id,
                user_id=ctx.user_id,
                feature="f",
                model="m",
                prompt_version="f@1",
                quota=quota,
            )

        try:
            await call(50)  # the last call of the day
            with pytest.raises(QuotaExceeded):
                await call(50)
            await call(1_000_000)  # a follow-up of a started turn is counted, not cut
        finally:
            await session.close()
    await purge_tenant(db_engine, org_id=ctx.org_id, user_id=ctx.user_id)
