"""coach service against the real DB with FakeLLMGateway streams."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway, TextPart
from recruitai.ai.prompts import fit
from recruitai.ai.prompts.coach import (
    JOB_FOCUS_OVERLAY,
    PROMPT_VERSION,
    SYSTEM_PROMPT_CAREER_COACH,
)
from recruitai.ai.prompts.language import with_language
from recruitai.core import inbox
from recruitai.core.email import FakeEmailSender
from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.core.telegram import FakeTelegram
from recruitai.modules.agents.connections.models import Connection
from recruitai.modules.agents.flows import engine
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.candidates.schemas import CVInformation, PersonalInfo, RawSkill
from recruitai.modules.coach import inbox as coach_inbox
from recruitai.modules.coach import repository, service
from recruitai.modules.coach.context import HISTORY_MAX_CHARS, HISTORY_MAX_MESSAGES
from recruitai.modules.identity import service as identity
from recruitai.modules.matching import service as matching
from recruitai.modules.matching.schemas import FitCheck
from tests.integration.coach_replies import replies
from tests.integration.test_agents import _create as agent
from tests.integration.test_flows import (
    agent_node,
    edge,
    input_node,
    make_flow,
    org_of,
    output_node,
    run_now,
)
from tests.integration.test_letters_service import _tenant
from tests.integration.test_matching_router import _add_profile
from tests.integration.test_reminders import _application, _user
from tests.unit.test_schemas import VALID


async def _say(
    db: AsyncSession, llm: FakeLLMGateway, org, conversation, text: str, *chunks: str
) -> str:
    llm.queue_stream(PROMPT_VERSION, list(chunks))
    out = [
        c
        async for c in replies(
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
    assert (
        first.system
        == with_language(SYSTEM_PROMPT_CAREER_COACH + JOB_FOCUS_OVERLAY, "en")
        and first.model == "smart"
    )
    assert first.feature == PROMPT_VERSION and first.schema is None
    p1 = _prompt(fake_llm)
    assert "Dev Python" in p1  # the job under discussion
    assert "Lucas Martel" not in p1  # the candidate's identity is never sent
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
        async for chunk in replies(
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


async def test_memory_and_situation_are_sent_fenced_and_counted(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    """ADR 0042: the coach knows what it was asked to keep and where the search stands."""
    from recruitai.modules.applications import service as applications
    from recruitai.modules.applications.schemas import ApplicationIn
    from recruitai.modules.candidates import service as candidates

    org, _ = await _tenant(db_session, "mem")
    await candidates.add_fact(
        db_session, org_id=org.id, text="Remote only, no consulting firms"
    )
    await applications.create_application(
        db_session,
        org_id=org.id,
        data=ApplicationIn(company_name="Acme", job_title="ML Engineer"),
    )
    conversation = await service.create_conversation(db_session, org_id=org.id)
    await _say(db_session, fake_llm, org, conversation, "Plan my week", "Ok.")
    p = _prompt(fake_llm)
    assert "<known_facts>" in p and "Remote only, no consulting firms" in p
    assert "<where_they_stand>" in p and "Tracker:" in p
    stored = await service.list_messages(
        db_session, org_id=org.id, conversation_id=conversation.id
    )
    counts = stored[-1].meta.context
    assert counts["memory"] == {"chars": 34, "truncated": False}  # "- " + the fact
    assert counts["situation"]["truncated"] is False


# --- the Assistant inbox (ADR 0042) ---------------------------------------------------------


async def _owner_with_cv(db: AsyncSession, tag: str):
    _, ctx = await _user(db, tag)
    await candidates_repo.upsert(
        db,
        org_id=ctx.org_id,
        document_id=None,
        info=CVInformation(
            personal_info=PersonalInfo(name="Ada"),
            formations=[],
            experiences=[],
            skills=[RawSkill(name="Python")],
        ),
    )
    return ctx


async def _inbox_items(db: AsyncSession, org_id) -> list[tuple[str, dict]]:
    conversation = await service.assistant_conversation(db, org_id=org_id)
    rows = await repository.list_messages(
        db, org_id=org_id, conversation_id=conversation.id, limit=50, offset=0
    )
    return [(m.content, (m.meta or {}).get("inbox")) for m in rows]


async def test_a_finished_run_posts_one_inbox_line_and_a_redelivery_posts_nothing(
    client, db_session: AsyncSession, fake_llm: FakeLLMGateway, task_app, ada
):
    await _add_profile(client, fake_llm, ada)
    org = await org_of(client, ada)
    i, o = input_node("n"), output_node("x")
    flow = await make_flow(client, ada, [i, o], [edge(i, o, {"x": "{{n}}"})])

    run = await run_now(client, db_session, fake_llm, ada, flow, {"n": "hi"}, org)
    await engine.execute(db_session, fake_llm, org_id=org, run_id=UUID(run["id"]))

    first = (await client.get("/api/v1/coach/assistant", headers=ada)).json()
    again = (await client.get("/api/v1/coach/assistant", headers=ada)).json()
    assert run["status"] == "done" and first["id"] == again["id"]
    assert first["kind"] == "assistant"
    msgs = (
        await client.get(
            f"/api/v1/coach/conversations/{first['id']}/messages", headers=ada
        )
    ).json()
    link = f"/automations/runs/{run['id']}"
    assert [(m["content"], m["meta"]["inbox"]) for m in msgs] == [
        ("F: done.", {"kind": "run_done", "link": link})
    ]

    # a failed run says so, with its fixed code (no reply queued: the model "breaks")
    x = await agent(client, ada)
    a, r = agent_node(x), output_node("r")
    broken = await make_flow(
        client,
        ada,
        [i, a, r],
        [edge(i, a, {"notes": "{{n}}"}), edge(a, r, {"r": "{{text}}"})],
    )
    failed = await run_now(client, db_session, fake_llm, ada, broken, {"n": "hi"}, org)
    assert failed["status"] == "failed"
    assert (await _inbox_items(db_session, org))[-1] == (
        "F: failed (step_failed).",
        {"kind": "run_failed", "link": f"/automations/runs/{failed['id']}"},
    )
    listed = (await client.get("/api/v1/coach/conversations", headers=ada)).json()
    assert [(c["id"], c["kind"]) for c in listed] == [(first["id"], "assistant")]


async def test_the_assistant_conversation_is_per_org_and_needs_a_cv(
    client, fake_llm: FakeLLMGateway, ada, bob
):
    await _add_profile(client, fake_llm, ada)
    mine = (await client.get("/api/v1/coach/assistant", headers=ada)).json()["id"]

    assert (await client.get("/api/v1/coach/assistant", headers=bob)).status_code == 422
    await _add_profile(client, fake_llm, bob)
    theirs = (await client.get("/api/v1/coach/assistant", headers=bob)).json()["id"]
    assert theirs != mine
    resp = await client.get(f"/api/v1/coach/conversations/{mine}/messages", headers=bob)
    assert resp.status_code == 404


async def test_the_telegram_mirror_is_queued_only_for_a_linked_chat(
    db_session: AsyncSession, task_app
):
    ctx = await _owner_with_cv(db_session, "tg")

    async def queued() -> list[dict]:
        rows = await db_session.execute(
            sql(
                "SELECT args FROM procrastinate_jobs"
                " WHERE task_name = 'coach:telegram_line' AND args->>'org_id' = :o"
            ),
            {"o": str(ctx.org_id)},
        )
        return [r[0] for r in rows.all()]

    async def post() -> None:
        await inbox.post(
            db_session,
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            kind="run_done",
            params={"name": "F"},
            link="/automations/runs/x",
        )

    await post()
    assert await queued() == []  # no linked chat: the inbox message only
    db_session.add(
        Connection(
            org_id=ctx.org_id,
            user_id=ctx.user_id,
            provider="telegram",
            status="active",
            chat_id=4242,
        )
    )
    await post()
    [job] = await queued()
    bot = FakeTelegram()
    code = await coach_inbox.mirror(
        db_session,
        bot,
        "https://app.test",
        org_id=ctx.org_id,
        user_id=ctx.user_id,
        message_id=UUID(job["message_id"]),
    )
    assert code is None
    assert bot.sent == [(4242, "F: done.\nhttps://app.test/automations/runs/x")]


async def test_the_daily_reminder_reaches_the_inbox_once_a_day(
    db_session: AsyncSession,
):
    ctx = await _owner_with_cv(db_session, "rem")
    now = datetime.now(UTC)
    await _application(
        db_session, ctx.org_id, "Quiet Inc", applied_at=now.date() - timedelta(days=7)
    )

    for _ in range(2):  # the task ran twice today
        await identity.send_application_reminders(
            db_session, FakeEmailSender(), now=now
        )

    assert await _inbox_items(db_session, ctx.org_id) == [
        (
            "Reminders: 1 follow-up(s) or interview(s) today.",
            {"kind": "reminder", "link": "/tracker"},
        )
    ]
