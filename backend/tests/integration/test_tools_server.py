"""The agent tools service (ADR 0043), reached over real MCP (streamable HTTP, in-process transport):
same answers as in-process, the tenant comes from the call's context, errors keep their code, and
nobody without an allowed token gets in."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.config import get_settings
from recruitai.core import tool_calls, tools
from recruitai.core.errors import NotFound
from recruitai.tools_server import Callers, create_app
from tests.integration.test_letters_service import _tenant

URL = "http://tools/mcp"


@asynccontextmanager
async def remote_tools(
    engine: AsyncEngine, llm: FakeLLMGateway, monkeypatch
) -> AsyncIterator[None]:
    """Turns the tools service on: every ``mcp`` tool now goes over HTTP to a real server app,
    which opens its own sessions (so it sees only committed rows, as in production)."""
    local = get_settings().model_copy(update={"tools_url": None, "env": "local"})

    async def llm_for(_db, _org, _user):
        return llm

    app = create_app(local, async_sessionmaker(engine, expire_on_commit=False), llm_for)
    on = get_settings().model_copy(update={"tools_url": URL})
    monkeypatch.setattr(tool_calls, "get_settings", lambda: on)
    monkeypatch.setattr(
        tool_calls,
        "http_client",
        lambda headers, timeout: httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), headers=headers, timeout=timeout
        ),
    )
    async with app.router.lifespan_context(app):
        yield


async def test_a_remote_tool_answers_like_the_local_one_for_the_callers_account_only(
    db_engine: AsyncEngine, fake_llm: FakeLLMGateway, monkeypatch
):
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        a, job = await _tenant(db, "mcpa")
        b, _ = await _tenant(db, "mcpb", profile=False)
        await (
            db.commit()
        )  # the service has its own session: it sees committed rows only
        try:
            call = tools.Call(db, fake_llm, a.id, a.id, None, {})
            local = await tools.handler("profile_read")(call)
            async with remote_tools(db_engine, fake_llm, monkeypatch):
                profile = tools.get("profile_read")
                assert tool_calls.remote(profile)
                assert await tool_calls.invoke(profile, call) == local
                assert local == {"summary": "", "skills": "Python"}
                # the tenant travels in the context: b has no profile and never sees a's
                with pytest.raises(tools.ToolFailed) as err:
                    await tool_calls.invoke(profile, tools.Call(db, fake_llm, b.id, b.id, None, {}))  # fmt: skip
                assert (err.value.code, err.value.status_code) == (
                    NotFound.code,
                    404,
                )  # as in-process
                # an AppError keeps its code across the network (a job tool with no job)
                lookup = tools.get("job_lookup")
                with pytest.raises(tools.ToolFailed) as err:
                    await tool_calls.invoke(lookup, call)
                assert err.value.code == "no_job"
                out = await tool_calls.invoke(lookup, tools.Call(db, fake_llm, a.id, a.id, job.id, {}))  # fmt: skip
                assert set(out) == set(lookup.outputs)
        finally:
            await db.rollback()
            await db.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": a.id, "b": b.id})  # fmt: skip
            await db.execute(text("DELETE FROM users WHERE firebase_uid IN ('fb-mcpa', 'fb-mcpb')"))  # fmt: skip
            await db.commit()


async def test_the_service_lists_its_tools_and_reports_alive_or_dead(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    fake_llm: FakeLLMGateway,
    monkeypatch,
):
    async with remote_tools(db_engine, fake_llm, monkeypatch):
        status = await tool_calls.status()
    assert status["remote"] and status["ok"]
    assert status["served"] == sorted(i for i, t in tools.all().items() if t.mcp)

    def dead(headers, timeout):
        raise httpx2.ConnectError("refused")

    monkeypatch.setattr(tool_calls, "http_client", dead)
    assert (await tool_calls.status())["ok"] is False
    with pytest.raises(tool_calls.ToolsUnavailable):
        await tool_calls.invoke(tools.get("job_search"), tools.Call(db_session, fake_llm, uuid4(), None, None, {}))  # fmt: skip


async def test_only_allowed_callers_get_in_and_production_needs_an_audience(
    monkeypatch,
):
    callers = Callers("https://tools.example", {"api@p.iam.gserviceaccount.com"})
    claims = {"email": "api@p.iam.gserviceaccount.com", "email_verified": True, "exp": 9e9}  # fmt: skip
    monkeypatch.setattr(callers, "_verify", lambda token: claims if token.startswith("good") else None)  # fmt: skip
    assert await callers.allowed("Bearer good")
    assert not await callers.allowed("Bearer forged")
    assert not await callers.allowed("")
    claims["email"] = "someone@else.com"
    assert not await callers.allowed("Bearer good2")  # a valid token of another account

    audience = {"env": "local", "tools_audience": "https://tools.example"}
    app = create_app(get_settings().model_copy(update=audience), None, None)
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (
            await c.get("/health")
        ).status_code == 200  # the startup probe has no token
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        assert (await c.post("/mcp", json=body)).status_code == 403
    prod = get_settings().model_copy(update={"env": "prod", "tools_audience": None})
    with pytest.raises(RuntimeError):
        create_app(prod, None, None)
