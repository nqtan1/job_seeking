from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.db import get_db
from recruitai.main import create_app
from tests.fixtures.llm import FakeLLMGateway
from tests.fixtures.storage import FakeStorage


@pytest.fixture
def app(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: FakeStorage
) -> FastAPI:
    """``create_app()`` with dependencies overridden. The LLM and storage fakes are exposed on
    ``app.state`` until their real dependency providers exist (P1-09, P1-11)."""
    application = create_app()

    async def _db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _db
    application.state.fake_llm = fake_llm
    application.state.fake_storage = fake_storage
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
