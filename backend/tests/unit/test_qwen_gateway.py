"""ai/qwen.py (P1-12b): mocked openai client against a fake local server — never a real call."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from recruitai.ai.gateway import FilePart, QuotaExceeded, TextPart
from recruitai.ai.qwen import QwenGateway
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
        "qwen_model_name": "qwen2.5-coder-14b",
        "ai_call_timeout_s": 5.0,
        "ai_daily_quota_per_user": 3,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def _mock_client(
    completion: object | None = None, side_effect: object | None = None
) -> MagicMock:
    client = MagicMock()
    call = AsyncMock()
    if side_effect is not None:
        call.side_effect = side_effect
    else:
        call.return_value = completion
    client.chat.completions.create = call
    return client


def _fake_completion(name: str = "Ada") -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = Extracted(name=name).model_dump_json()
    completion.usage.prompt_tokens = 7
    completion.usage.completion_tokens = 3
    return completion


async def _org_user(db_session):
    ctx = await get_org_context(
        CurrentUser(
            firebase_uid=f"uid-qwen-{uuid4().hex[:8]}", email="qwen@example.test"
        ),
        db_session,
        x_org_id=None,
    )
    return ctx.org_id, ctx.user_id


async def test_generate_returns_parsed_and_records_one_ai_call(db_session):
    org_id, user_id = await _org_user(db_session)
    client = _mock_client(completion=_fake_completion())
    gateway = QwenGateway(
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
        feature="cv_extract@1",
    )

    assert result == Extracted(name="Ada")
    row = (
        await db_session.execute(select(AiCall).where(AiCall.user_id == user_id))
    ).scalar_one()
    assert row.feature == "cv_extract"
    assert row.prompt_version == "cv_extract@1"
    assert row.model == "qwen2.5-coder-14b"
    assert row.status == "ok"
    assert (row.input_tokens, row.output_tokens) == (7, 3)


async def test_image_file_part_is_base64_encoded():
    from recruitai.ai.qwen import _to_openai_content

    block = _to_openai_content(FilePart(data=b"\x89PNG", mime_type="image/png"))
    assert block["type"] == "image_url"
    assert block["image_url"]["url"].startswith("data:image/png;base64,")


def test_non_image_file_part_is_rejected():
    from recruitai.ai.qwen import _to_openai_content

    with pytest.raises(ValueError, match="only accepts image"):
        _to_openai_content(FilePart(data=b"%PDF-", mime_type="application/pdf"))


async def test_mismatched_schema_raises_upstream_unavailable(db_session):
    class Other(BaseModel):
        n: int

    org_id, user_id = await _org_user(db_session)
    completion = MagicMock()
    completion.choices[0].message.content = Other(n=1).model_dump_json()
    completion.usage = None
    client = _mock_client(completion=completion)
    gateway = QwenGateway(
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
    client = _mock_client(completion=_fake_completion())
    gateway = QwenGateway(
        client=client,
        settings=_settings(ai_daily_quota_per_user=1),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    await gateway.generate(
        schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
    )

    with pytest.raises(QuotaExceeded):
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )

    assert client.chat.completions.create.await_count == 1


async def test_call_timeout_is_enforced(db_session):
    import asyncio

    async def _hangs(**kwargs):
        await asyncio.sleep(10)

    org_id, user_id = await _org_user(db_session)
    client = _mock_client()
    client.chat.completions.create = AsyncMock(side_effect=_hangs)
    gateway = QwenGateway(
        client=client,
        settings=_settings(ai_call_timeout_s=0.01),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    with pytest.raises(UpstreamUnavailable) as exc_info:
        await gateway.generate(
            schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
        )
    assert exc_info.value.code == "ai_timeout"


async def test_server_errors_and_empty_choices_are_clean_upstream_errors(db_session):
    import httpx
    from openai import APIConnectionError

    org_id, user_id = await _org_user(db_session)
    no_choices = MagicMock()
    no_choices.choices = []
    no_choices.usage = None
    expected = {
        "ai_unavailable": APIConnectionError(
            request=httpx.Request("POST", "http://x.test")
        ),
        "ai_response_invalid": None,
    }
    for code, error in expected.items():
        client = _mock_client(completion=no_choices, side_effect=error)
        gateway = QwenGateway(
            client=client,
            settings=_settings(),
            db=db_session,
            org_id=org_id,
            user_id=user_id,
        )
        with pytest.raises(UpstreamUnavailable) as exc_info:
            await gateway.generate(
                schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
            )
        assert exc_info.value.code == code


async def test_pdf_and_text_files_become_text_and_only_images_need_vision():
    from recruitai.ai.qwen import _text_only

    pdf = FilePart(
        data=(Path(__file__).parent.parent / "fixtures" / "cv_sample.pdf").read_bytes(),
        mime_type="application/pdf",
    )
    parts, has_image = await _text_only(
        [pdf, FilePart(data=b"plain cv", mime_type="text/plain")]
    )
    assert not has_image
    assert all(isinstance(p, TextPart) for p in parts)
    assert "Ada Lovelace" in parts[0].text and parts[1].text == "plain cv"

    _, has_image = await _text_only([FilePart(data=b"\x89PNG", mime_type="image/png")])
    assert has_image


async def test_pdf_without_text_layer_is_a_clean_validation_error():
    from recruitai.ai.qwen import _text_only
    from recruitai.core.errors import ValidationFailed

    for data in (b"%PDF-1.4 not really a pdf", b""):
        with pytest.raises(ValidationFailed):
            await _text_only([FilePart(data=data, mime_type="application/pdf")])


async def test_no_db_transaction_is_open_while_the_model_call_runs(db_session):
    """A slow model call must not hold a transaction open: Postgres kills idle-in-transaction
    sessions, which turned a plain timeout into an opaque 500 against the local servers."""
    seen: list[bool] = []

    async def _parse(**kwargs):
        seen.append(db_session.in_transaction())
        return _fake_completion()

    org_id, user_id = await _org_user(db_session)
    client = _mock_client(side_effect=_parse)
    gateway = QwenGateway(
        client=client,
        settings=_settings(),
        db=db_session,
        org_id=org_id,
        user_id=user_id,
    )

    await gateway.generate(
        schema=Extracted, system="s", parts=[TextPart(text="x")], feature="f"
    )

    assert seen == [False]


async def _qwen_chunks(*texts: str, fail: Exception | None = None, hang: bool = False):
    import asyncio

    for text in texts:
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content=text))], usage=None)
    if fail is not None:
        raise fail
    if hang:
        await asyncio.sleep(10)
    # vLLM/OpenAI send the token usage in a final chunk with no choices
    yield MagicMock(choices=[], usage=MagicMock(prompt_tokens=9, completion_tokens=5))


def _qwen_stream_gateway(db, org_id, user_id, chunks, **settings):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=chunks)
    gateway = QwenGateway(
        client=client,
        settings=_settings(**settings),
        db=db,
        org_id=org_id,
        user_id=user_id,
    )
    return gateway, client


async def test_stream_yields_text_and_records_one_ok_call_with_tokens(db_session):
    org_id, user_id = await _org_user(db_session)
    gateway, client = _qwen_stream_gateway(
        db_session, org_id, user_id, _qwen_chunks("Bon", "jour")
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
    assert (row.status, row.input_tokens, row.output_tokens) == ("ok", 9, 5)
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["stream"] is True and kwargs["stream_options"] == {
        "include_usage": True
    }
    # free text: unlike generate(), no JSON schema is appended to the system prompt
    assert kwargs["messages"][0] == {"role": "system", "content": "s"}


async def test_stream_over_quota_and_midstream_failure_and_idle_timeout(db_session):
    import httpx
    from openai import APIConnectionError

    org_id, user_id = await _org_user(db_session)

    gateway, client = _qwen_stream_gateway(
        db_session, org_id, user_id, _qwen_chunks("x"), ai_daily_quota_per_user=0
    )
    with pytest.raises(QuotaExceeded):
        async for _ in gateway.stream(
            system="s", parts=[TextPart(text="hi")], feature="coach@1"
        ):
            pass
    assert client.chat.completions.create.await_count == 0

    boom = APIConnectionError(request=httpx.Request("POST", "http://x.test"))
    gateway, _ = _qwen_stream_gateway(
        db_session, org_id, user_id, _qwen_chunks("Bon", fail=boom)
    )
    got: list[str] = []
    with pytest.raises(UpstreamUnavailable) as err:
        async for chunk in gateway.stream(
            system="s", parts=[TextPart(text="hi")], feature="coach@1"
        ):
            got.append(chunk)
    assert got == ["Bon"] and err.value.code == "ai_unavailable"

    gateway, _ = _qwen_stream_gateway(
        db_session,
        org_id,
        user_id,
        _qwen_chunks("Bon", hang=True),
        ai_call_timeout_s=0.05,
    )
    with pytest.raises(UpstreamUnavailable) as err:
        async for _ in gateway.stream(
            system="s", parts=[TextPart(text="hi")], feature="coach@1"
        ):
            pass
    assert err.value.code == "ai_timeout"


def test_any_failure_reading_a_pdf_is_a_validation_error_not_a_500(monkeypatch):
    from recruitai.ai import qwen
    from recruitai.core.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        qwen._pdf_text(b"%PDF-1.4 not really a pdf")

    class Weird:
        def __init__(self, *_: object) -> None:
            raise KeyError("/Root")  # pypdf can raise things that are not PyPdfError

    monkeypatch.setattr(qwen, "PdfReader", Weird)
    with pytest.raises(ValidationFailed):
        qwen._pdf_text(b"%PDF-1.4")
