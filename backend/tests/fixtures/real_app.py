"""Fixtures for tests that need the worker or a streaming response to see *committed* data:
an app whose DB session is a fresh, really-committing one per request (like production),
and two emulator users whose data is deleted afterwards. The default ``app``/``client``
fixtures wrap everything in one rolled-back transaction, which hides that lifecycle."""

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.storage import LocalStorage, get_storage_dependency
from recruitai.main import create_app
from recruitai.modules.jobs.router import get_job_provider
from tests.fixtures.jobs import FakeJobProvider


@pytest.fixture
async def real_app(
    db_engine: AsyncEngine,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    fake_job_provider: FakeJobProvider,
) -> AsyncIterator[FastAPI]:
    app = create_app()

    async def _db() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_storage_dependency] = lambda: fake_storage
    app.dependency_overrides[verify_app_check] = lambda: None
    app.dependency_overrides[get_llm_gateway] = lambda: fake_llm
    app.dependency_overrides[get_job_provider] = lambda: fake_job_provider
    yield app


@pytest.fixture
async def real_client(real_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=real_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def users(
    emulator_token, db_engine: AsyncEngine
) -> AsyncIterator[dict[str, dict[str, str]]]:
    tag = uuid4().hex[:8]
    uids = {"ada": f"uid-ada-{tag}", "bob": f"uid-bob-{tag}"}
    yield {
        who: {
            "Authorization": f"Bearer {emulator_token(uid, f'{who}-{tag}@example.com')}"
        }
        for who, uid in uids.items()
    }
    async with (
        db_engine.begin() as conn
    ):  # org first: it cascades to everything the test made
        for uid in uids.values():
            await conn.execute(
                text(
                    "DELETE FROM organizations WHERE id IN (SELECT m.org_id FROM memberships m"
                    " JOIN users u ON u.id = m.user_id WHERE u.firebase_uid = :u)"
                ),
                {"u": uid},
            )
            await conn.execute(
                text("DELETE FROM users WHERE firebase_uid = :u"), {"u": uid}
            )
