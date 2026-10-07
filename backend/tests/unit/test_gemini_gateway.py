"""ai/gemini.py (P1-12): mocked google-genai client — never a real network call."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel
from sqlalchemy import select

from recruitai.ai.gateway import QuotaExceeded, TextPart
from recruitai.ai.gemini import GeminiGateway
from recruitai.ai.usage import AiCall
from recruitai.config import Settings
from recruitai.core.auth import CurrentUser
from recruitai.core.errors import UpstreamUnavailable
from recruitai.core.tenancy import get_org_context


class Extracted(BaseModel):
    name: str


def _settings(**overrides) -> Settings:
    base = {
        "env": "local",
        "database_url": "postgresql+psycopg://u:p@localhost/x_test",
        "firebase_project_id": "demo",
        "ai_max_retries": 2,
        "ai_call_timeout_s": 5.0,
        "ai_daily_quota_per_user": 3,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def _mock_client(
    response: object | None = None, side_effect: object | None = None
) -> MagicMock:
    client = MagicMock()
    call = AsyncMock()
    if side_effect is not None:
        call.side_effect = side_effect
    else:
        call.return_value = response
    client.aio.models.generate_content = call
    return client


def _fake_response(name: str = "Ada") -> MagicMock:
    resp = MagicMock()
    resp.parsed = Extracted(name=name)
    resp.usage_metadata.prompt_token_count = 10
    resp.usage_metadata.candidates_token_count = 5
    return resp


async def _org_user(db_session):
    ctx = await get_org_context(
        CurrentUser(
            firebase_uid=f"uid-gem-{uuid4().hex[:8]}", email="gem@example.test"
        ),
        db_session,
        x_org_id=None,
    )
    return ctx.org_id, ctx.user_id


async def test_generate_returns_parsed_and_records_one_ai_call(db_session):
    org_id, user_id = await _org_user(db_session)
    client = _mock_client(response=_fake_response())
    gateway = GeminiGateway(
        client=client,
        settings=_settings(),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    result = await gateway.generate(
        schema=Extracted,
        system="extract",
        parts=[TextPart(text="cv text")],
        feature="cv_extract@3",
    )

    assert result == Extracted(name="Ada")
    client.aio.models.generate_content.assert_awaited_once()
    row = (
        await db_session.execute(select(AiCall).where(AiCall.user_id == user_id))
    ).scalar_one()
    assert row.feature == "cv_extract"
    assert row.prompt_version == "cv_extract@3"
    assert row.status == "ok"
    assert row.input_tokens == 10
    assert row.output_tokens == 5
    assert row.model == "gemini-2.5-flash-lite"


async def test_retries_on_server_error_then_succeeds(db_session, monkeypatch):
    monkeypatch.setattr("recruitai.ai.gemini.asyncio.sleep", AsyncMock())
    org_id, user_id = await _org_user(db_session)
    client = _mock_client(
        side_effect=[ServerError(503, {}), ServerError(503, {}), _fake_response()]
    )
    gateway = GeminiGateway(
        client=client,
        settings=_settings(),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    result = await gateway.generate(
        schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
    )

    assert result == Extracted(name="Ada")
    assert client.aio.models.generate_content.await_count == 3


async def test_non_retryable_client_error_raises_immediately(db_session):
    org_id, user_id = await _org_user(db_session)
    client = _mock_client(side_effect=ClientError(400, {}))
    gateway = GeminiGateway(
        client=client,
        settings=_settings(),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    with pytest.raises(UpstreamUnavailable) as err:
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )

    assert err.value.code == "ai_unavailable"
    assert client.aio.models.generate_content.await_count == 1
    row = (
        await db_session.execute(select(AiCall).where(AiCall.user_id == user_id))
    ).scalar_one()
    assert row.status == "error"


async def test_exhausts_retries_and_raises(db_session, monkeypatch):
    monkeypatch.setattr("recruitai.ai.gemini.asyncio.sleep", AsyncMock())
    org_id, user_id = await _org_user(db_session)
    client = _mock_client(side_effect=ServerError(503, {}))
    gateway = GeminiGateway(
        client=client,
        settings=_settings(ai_max_retries=2),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    with pytest.raises(UpstreamUnavailable) as err:
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )

    assert err.value.code == "ai_unavailable"
    assert client.aio.models.generate_content.await_count == 3  # 1 + 2 retries


async def test_call_timeout_is_enforced(db_session):
    import asyncio

    async def _hangs(**kwargs):
        await asyncio.sleep(10)

    org_id, user_id = await _org_user(db_session)
    client = _mock_client()
    client.aio.models.generate_content = AsyncMock(side_effect=_hangs)
    gateway = GeminiGateway(
        client=client,
        settings=_settings(ai_call_timeout_s=0.01, ai_max_retries=0),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    with pytest.raises(UpstreamUnavailable) as exc_info:
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )
    assert exc_info.value.code == "ai_timeout"


async def test_mismatched_schema_raises_upstream_unavailable(db_session):
    class Other(BaseModel):
        n: int

    org_id, user_id = await _org_user(db_session)
    resp = MagicMock()
    resp.parsed = Other(n=1)  # not an Extracted
    resp.usage_metadata = None
    client = _mock_client(response=resp)
    gateway = GeminiGateway(
        client=client,
        settings=_settings(),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    with pytest.raises(UpstreamUnavailable):
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )


async def test_quota_exceeded_raises_before_calling_the_model(db_session):
    org_id, user_id = await _org_user(db_session)
    client = _mock_client(response=_fake_response())
    gateway = GeminiGateway(
        client=client,
        settings=_settings(ai_daily_quota_per_user=1),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    await gateway.generate(
        schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
    )  # first call: within quota

    with pytest.raises(QuotaExceeded):
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )

    assert (
        client.aio.models.generate_content.await_count == 1
    )  # never called the 2nd time


async def _gemini_chunks(
    *texts: str, fail: Exception | None = None, hang: bool = False
):
    import asyncio

    for i, text in enumerate(texts):
        usage = MagicMock(prompt_token_count=11, candidates_token_count=4)
        last = i == len(texts) - 1
        yield MagicMock(text=text, usage_metadata=usage if last and not fail else None)
    if fail is not None:
        raise fail
    if hang:
        await asyncio.sleep(10)


def _stream_gateway(db, org_id, user_id, chunks, **settings):
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(return_value=chunks)
    gateway = GeminiGateway(
        client=client,
        settings=_settings(**settings),
        db=db,
        org_id=org_id,
        user_id=user_id,
    )
    return gateway, client


async def test_stream_yields_text_and_records_one_ok_call_with_tokens(db_session):
    org_id, user_id = await _org_user(db_session)
    gateway, client = _stream_gateway(
        db_session, org_id, user_id, _gemini_chunks("Bon", "jour")
    )

    out = [
        c
        async for c in gateway.stream(
            system="s", parts=[TextPart(text="hi")], feature="coach@1"
        )
    ]

    assert out == ["Bon", "jour"]
    row = (
        await db_session.execute(select(AiCall).where(AiCall.user_id == user_id))
    ).scalar_one()
    assert (row.status, row.input_tokens, row.output_tokens) == ("ok", 11, 4)
    assert (row.feature, row.prompt_version) == ("coach", "coach@1")
    assert client.aio.models.generate_content_stream.await_count == 1


async def test_stream_over_quota_raises_before_calling_the_model(db_session):
    org_id, user_id = await _org_user(db_session)
    gateway, client = _stream_gateway(
        db_session, org_id, user_id, _gemini_chunks("x"), ai_daily_quota_per_user=0
    )
    with pytest.raises(QuotaExceeded):
        async for _ in gateway.stream(
            system="s", parts=[TextPart(text="hi")], feature="coach@1"
        ):
            pass
    assert client.aio.models.generate_content_stream.await_count == 0


async def test_stream_failure_mid_reply_is_a_clean_error_and_the_call_is_marked_failed(
    db_session,
):
    org_id, user_id = await _org_user(db_session)
    gateway, _ = _stream_gateway(
        db_session, org_id, user_id, _gemini_chunks("Bon", fail=ServerError(503, {}))
    )
    got: list[str] = []
    with pytest.raises(UpstreamUnavailable) as err:
        async for chunk in gateway.stream(
            system="s", parts=[TextPart(text="hi")], feature="coach@1"
        ):
            got.append(chunk)
    assert got == ["Bon"] and err.value.code == "ai_unavailable"
    row = (
        await db_session.execute(select(AiCall).where(AiCall.user_id == user_id))
    ).scalar_one()
    assert row.status == "error"


async def test_stream_idle_timeout_is_enforced_per_chunk(db_session):
    org_id, user_id = await _org_user(db_session)
    gateway, _ = _stream_gateway(
        db_session,
        org_id,
        user_id,
        _gemini_chunks("Bon", hang=True),
        ai_call_timeout_s=0.05,
    )
    with pytest.raises(UpstreamUnavailable) as err:
        async for _ in gateway.stream(
            system="s", parts=[TextPart(text="hi")], feature="coach@1"
        ):
            pass
    assert err.value.code == "ai_timeout"


async def test_a_dropped_connection_is_retried_then_a_clean_upstream_error(
    db_session, monkeypatch
):
    import httpx

    monkeypatch.setattr("recruitai.ai.gemini.asyncio.sleep", AsyncMock())
    org_id, user_id = await _org_user(db_session)
    client = _mock_client(side_effect=httpx.ConnectError("connection reset"))
    gateway = GeminiGateway(
        client=client, settings=_settings(ai_max_retries=2), db=db_session,
        org_id=org_id, user_id=user_id,
    )  # fmt: skip

    with pytest.raises(UpstreamUnavailable) as err:
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )

    assert err.value.code == "ai_unavailable"
    assert (
        client.aio.models.generate_content.await_count == 3
    )  # 1 try + 2 retries, not a bare 500
