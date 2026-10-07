from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.dependencies import get_llm_gateway
from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.app_check import verify_app_check
from recruitai.core.db import get_db
from recruitai.core.storage import LocalStorage, Storage, get_storage_dependency
from recruitai.main import create_app
from recruitai.modules.jobs.router import get_job_provider
from tests.fixtures.jobs import FakeJobProvider


@pytest.fixture
def app(
    db_session: AsyncSession,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    fake_job_provider: FakeJobProvider,
) -> FastAPI:
    """``create_app()`` with the DB session, storage and LLM gateway overridden."""
    application = create_app()

    async def _db() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _storage() -> Storage:
        return fake_storage

    application.dependency_overrides[get_db] = _db
    application.dependency_overrides[get_storage_dependency] = _storage
    # Real App Check tokens need a real Firebase project; tests that care pop this override.
    application.dependency_overrides[verify_app_check] = lambda: None
    application.dependency_overrides[get_llm_gateway] = lambda: fake_llm
    application.dependency_overrides[get_job_provider] = lambda: fake_job_provider
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
