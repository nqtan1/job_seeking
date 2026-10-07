"""coach service against the real DB with FakeLLMGateway streams (P2-23c)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway, TextPart
from recruitai.ai.prompts import fit
from recruitai.ai.prompts.coach import PROMPT_VERSION, SYSTEM_PROMPT_CAREER_COACH
from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.modules.coach import repository, service
from recruitai.modules.coach.service import HISTORY_MAX_CHARS, HISTORY_MAX_MESSAGES
from recruitai.modules.matching import service as matching
from recruitai.modules.matching.schemas import FitCheck
from tests.integration.test_letters_service import _tenant
from tests.unit.test_schemas import VALID


async def _say(
    db: AsyncSession, llm: FakeLLMGateway, org, conversation, text: str, *chunks: str
) -> str:
    llm.queue_stream(PROMPT_VERSION, list(chunks))
    out = [
        c
        async for c in service.stream_reply(
            db, llm, org_id=org.id, conversation_id=conversation.id, content=text
        )
    ]
    return "".join(out)


def _prompt(llm: FakeLLMGateway) -> str:
    return " ".join(p.text for p in llm.calls[-1].parts if isinstance(p, TextPart))


async def test_three_turns_each_store_exactly_two_messages_and_send_the_history(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    org, job = await _tenant(db_session, "a")
    fake_llm.queue(fit.PROMPT_VERSION, FitCheck.model_validate(VALID))
    await matching.analyze(db_session, fake_llm, org_id=org.id, job_id=job.id)
    conversation = await service.create_conversation(
        db_session, org_id=org.id, job_id=job.id
    )

    r1 = await _say(
        db_session,
        fake_llm,
        org,
        conversation,
        "Que penses-tu de mon CV ?",
        "Votre ",
        "CV est solide.",
    )
    assert r1 == "Votre CV est solide."
    first = fake_llm.calls[-1]
    assert first.system == SYSTEM_PROMPT_CAREER_COACH and first.model == "smart"
    assert first.feature == PROMPT_VERSION and first.schema is None
    p1 = _prompt(fake_llm)
    assert (
        "Lucas Martel" in p1 and "Dev Python" in p1
    )  # profile and job under discussion
    assert "Good stack match" in p1  # the latest fit report is part of the context
    assert "(no messages yet)" in p1

    await _say(
        db_session,
        fake_llm,
        org,
        conversation,
        "Quelles compétences apprendre ?",
        "Docker.",
    )
    p2 = _prompt(fake_llm)
    assert (
        "[candidate] Que penses-tu de mon CV ?" in p2
        and "[coach] Votre CV est solide." in p2
    )

    await _say(db_session, fake_llm, org, conversation, "Merci !", "Avec plaisir.")
    p3 = _prompt(fake_llm)
    assert "[coach] Docker." in p3 and "Merci !" in p3

    messages = await service.list_messages(
        db_session, org_id=org.id, conversation_id=conversation.id
    )
    assert [(m.role, m.content) for m in messages] == [
        ("user", "Que penses-tu de mon CV ?"), ("assistant", "Votre CV est solide."),
        ("user", "Quelles compétences apprendre ?"), ("assistant", "Docker."),
        ("user", "Merci !"), ("assistant", "Avec plaisir."),
    ]  # fmt: skip


async def test_refusals_cost_no_model_call_and_other_orgs_see_nothing(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, job_a = await _tenant(db_session, "a")
    b, _ = await _tenant(db_session, "b")
    bare, _ = await _tenant(db_session, "bare", profile=False)
    conversation = await service.create_conversation(db_session, org_id=a.id)

    for text in ("", "   ", "x" * 4001):
        with pytest.raises(ValidationFailed):
            await _say(db_session, fake_llm, a, conversation, text)
    with pytest.raises(NotFound):  # another org's conversation
        await _say(db_session, fake_llm, b, conversation, "hello")
    with pytest.raises(NotFound):
        await service.list_messages(
            db_session, org_id=b.id, conversation_id=conversation.id
        )
    with pytest.raises(NotFound):  # unknown conversation
        await service.get_conversation(
            db_session, org_id=a.id, conversation_id=job_a.id
        )
    with pytest.raises(NotFound):  # B cannot start a conversation about A's job
        await service.create_conversation(db_session, org_id=b.id, job_id=job_a.id)
    with pytest.raises(ValidationFailed):  # no profile yet
        await service.create_conversation(db_session, org_id=bare.id)
    assert fake_llm.calls == []


async def test_a_failed_or_empty_reply_stores_nothing_and_a_retry_works(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    org, _ = await _tenant(db_session, "a")
    conversation = await service.create_conversation(db_session, org_id=org.id)

    fake_llm.queue_stream(
        PROMPT_VERSION,
        ["Bon"],
        error=UpstreamUnavailable("The AI provider timed out.", code="ai_timeout"),
    )
    got: list[str] = []
    with pytest.raises(UpstreamUnavailable):
        async for chunk in service.stream_reply(
            db_session,
            fake_llm,
            org_id=org.id,
            conversation_id=conversation.id,
            content="Salut",
        ):
            got.append(chunk)
    assert got == ["Bon"]  # the client saw a partial reply, then the error

    with pytest.raises(UpstreamUnavailable) as err:
        await _say(
            db_session, fake_llm, org, conversation, "Salut", "  ", ""
        )  # nothing usable
    assert err.value.code == "ai_response_invalid"
    assert (
        await service.list_messages(
            db_session, org_id=org.id, conversation_id=conversation.id
        )
        == []
    )

    assert (
        await _say(db_session, fake_llm, org, conversation, "Salut", "Bonjour !")
        == "Bonjour !"
    )
    messages = await service.list_messages(
        db_session, org_id=org.id, conversation_id=conversation.id
    )
    assert [m.role for m in messages] == [
        "user",
        "assistant",
    ]  # the retry stored exactly one turn


async def test_a_very_long_conversation_only_sends_a_bounded_window(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    org, _ = await _tenant(db_session, "a")
    conversation = await service.create_conversation(db_session, org_id=org.id)
    for i in range(40):  # 80 stored messages of ~300 chars
        await repository.add_turn(
            db_session, org_id=org.id, conversation_id=conversation.id,
            user_text=f"question {i} " + "x" * 300, assistant_text=f"answer {i} " + "y" * 300,
        )  # fmt: skip

    await _say(db_session, fake_llm, org, conversation, "Et maintenant ?", "Réponse.")

    sent = _prompt(fake_llm)
    history = sent.split("<conversation_so_far>")[1].split("</conversation_so_far>")[0]
    assert (
        "answer 39" in history and "question 0" not in history
    )  # newest kept, oldest dropped
    assert (
        history.count("[candidate]") + history.count("[coach]") <= HISTORY_MAX_MESSAGES
    )
    assert (
        len(history) <= HISTORY_MAX_CHARS + 20 * HISTORY_MAX_MESSAGES
    )  # chars + labels


async def test_message_order_is_stable_within_a_turn(db_session: AsyncSession):
    org, _ = await _tenant(db_session, "a")
    conversation = await service.create_conversation(db_session, org_id=org.id)
    for _ in range(5):
        await repository.add_turn(
            db_session, org_id=org.id, conversation_id=conversation.id,
            user_text="q", assistant_text="a",
        )  # fmt: skip
    messages = await service.list_messages(
        db_session, org_id=org.id, conversation_id=conversation.id
    )
    assert [m.role for m in messages] == ["user", "assistant"] * 5


async def test_one_huge_message_is_clipped_instead_of_wiping_the_whole_history(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    org, _ = await _tenant(db_session, "a")
    conversation = await service.create_conversation(db_session, org_id=org.id)
    await repository.add_turn(
        db_session, org_id=org.id, conversation_id=conversation.id,
        user_text="early question", assistant_text="early answer",
    )  # fmt: skip
    await repository.add_turn(
        db_session, org_id=org.id, conversation_id=conversation.id,
        user_text="long question", assistant_text="z" * 9000,  # far over the whole budget
    )  # fmt: skip

    await _say(db_session, fake_llm, org, conversation, "And now?", "Reply.")

    history = (
        _prompt(fake_llm)
        .split("<conversation_so_far>")[1]
        .split("</conversation_so_far>")[0]
    )
    assert (
        "early question" in history and "early answer" in history
    )  # older turns survive
    assert (
        "[…]" in history and history.count("z") <= HISTORY_MAX_CHARS // 3
    )  # the huge one is clipped
