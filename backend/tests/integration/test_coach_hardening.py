"""Coach edge cases that need real connections or an abandoned stream."""

import asyncio
from unittest.mock import ANY
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.gateway import BackendCapabilities, FakeLLMGateway, TextDelta
from recruitai.ai.prompts.coach import PROMPT_VERSION
from recruitai.config import get_settings
from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.candidates.schemas import CVInformation, PersonalInfo, RawSkill
from recruitai.modules.coach import service
from tests.fixtures.db import purge_tenant
from tests.integration.coach_replies import replies
from tests.integration.test_letters_service import _tenant


async def test_an_abandoned_reply_stores_nothing_and_the_conversation_still_works(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    """The client disconnects after the first token: the stream is closed, not finished."""
    org, _ = await _tenant(db_session, "a")
    conversation = await service.create_conversation(db_session, org_id=org.id)
    fake_llm.queue_stream(PROMPT_VERSION, ["Bon", "jour", " à tous"])

    stream = service.stream_reply(
        db_session,
        fake_llm,
        get_settings(),
        org_id=org.id,
        conversation_id=conversation.id,
        content="Salut",
    )
    assert (await anext(stream))[0] == "context"
    assert await anext(stream) == ("token", {"text": "Bon"})
    await stream.aclose()  # what the server does when the connection drops

    assert (
        await service.list_messages(
            db_session, org_id=org.id, conversation_id=conversation.id
        )
        == []
    )
    fake_llm.queue_stream(PROMPT_VERSION, ["Bonjour !"])
    retried = [
        c
        async for c in replies(
            db_session,
            fake_llm,
            org_id=org.id,
            conversation_id=conversation.id,
            content="Salut",
        )
    ]
    assert "".join(retried) == "Bonjour !"
    stored = await service.list_messages(
        db_session, org_id=org.id, conversation_id=conversation.id
    )
    assert [m.role for m in stored] == ["user", "assistant"]


async def test_simultaneous_messages_in_one_conversation_never_interleave(
    db_engine: AsyncEngine,
):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        ctx = await get_org_context(
            CurrentUser(firebase_uid=f"uid-{uuid4().hex[:8]}", email="c@example.test"),
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
        conversation = await service.create_conversation(session, org_id=ctx.org_id)

    async def one_turn(i: int) -> None:
        llm = FakeLLMGateway()
        llm.queue_stream(PROMPT_VERSION, [f"answer {i}"])
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            async for _ in replies(
                session,
                llm,
                org_id=ctx.org_id,
                conversation_id=conversation.id,
                content=f"q{i}",
            ):
                pass

    try:
        await asyncio.gather(*(one_turn(i) for i in range(6)))
        async with AsyncSession(db_engine) as session:
            messages = await service.list_messages(
                session, org_id=ctx.org_id, conversation_id=conversation.id
            )
        assert [m.role for m in messages] == [
            "user",
            "assistant",
        ] * 6  # strictly paired
        for user, assistant in zip(messages[::2], messages[1::2], strict=True):
            assert assistant.content == user.content.replace(
                "q", "answer "
            )  # each reply follows its question
    finally:
        await purge_tenant(db_engine, org_id=ctx.org_id, user_id=ctx.user_id)


class _SpyGateway:
    """Records whether the model stream was closed (its ``finally`` runs: the gateway uses it
    to record the call's outcome)."""

    def __init__(self) -> None:
        self.closed = False

    def capabilities(self, feature: str | None = None) -> BackendCapabilities:
        return BackendCapabilities()

    def model_name(self, *_: object, **__: object) -> str:
        return "spy"

    async def converse(self, **_: object):
        try:
            yield TextDelta("Bon")
            yield TextDelta("jour")
        finally:
            self.closed = True


async def test_closing_the_reply_closes_the_model_stream_immediately(
    db_session: AsyncSession,
):
    org, _ = await _tenant(db_session, "a")
    conversation = await service.create_conversation(db_session, org_id=org.id)
    spy = _SpyGateway()

    stream = service.stream_reply(
        db_session,
        spy,  # type: ignore[arg-type]
        get_settings(),
        org_id=org.id,
        conversation_id=conversation.id,
        content="Salut",
    )
    assert await anext(stream) == ("context", ANY)
    assert await anext(stream) == ("token", {"text": "Bon"})
    assert spy.closed is False
    await stream.aclose()  # the client went away

    assert spy.closed is True  # not "whenever the garbage collector gets to it"
