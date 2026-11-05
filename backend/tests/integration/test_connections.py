"""Connections (ADR 0036): linking Telegram with a one-time code, sending only to the linked chat."""

from uuid import UUID

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.telegram import FakeTelegram, Update
from recruitai.modules.agents.blocks import tools
from recruitai.modules.agents.connections.router import bot
from recruitai.modules.agents.flows import engine
from tests.e2e_radar_fakes import Provider
from tests.integration.test_flows import (
    BASE,
    edge,
    input_node,
    make_flow,
    org_of,
    output_node,
    tool_node,
)


async def test_telegram_links_with_a_one_time_code_and_a_flow_messages_only_that_chat(
    client, app, db_session, fake_llm: FakeLLMGateway, task_app, ada, bob
):
    from recruitai.core.email import FakeEmailSender

    tg = FakeTelegram()
    app.dependency_overrides[bot] = lambda: tg
    link = lambda who: client.post(f"{BASE}/connections/telegram/link", headers=who)
    check = lambda who: client.post(f"{BASE}/connections/telegram/check", headers=who)
    state = lambda r: {c["provider"]: c["status"] for c in r.json()["items"]}

    # a message from the bot's side can do nothing before a link is started
    assert (await client.get(f"{BASE}/connections", headers=ada)).json()[
        "telegram_available"
    ]
    tg.inbox.append(Update(1, 111, "/start guess"))
    assert state(await check(ada)) == {}

    started = (await link(ada)).json()
    code = started["url"].split("?start=")[1]
    assert started["url"].startswith("https://t.me/recruitai_test_bot?start=")
    assert state(await client.get(f"{BASE}/connections", headers=ada)) == {
        "telegram": "pending"
    }

    # a wrong code and plain text link nothing; the right code links, once
    tg.inbox += [Update(2, 222, "/start nope"), Update(3, 333, "hello")]
    assert state(await check(ada)) == {"telegram": "pending"}
    tg.inbox.append(Update(4, 444, f"/start {code}"))
    assert state(await check(ada)) == {"telegram": "active"}
    assert [c for c, _ in tg.sent] == [444] and "/stop" in tg.sent[0][1]
    tg.inbox.append(Update(5, 555, f"/start {code}"))  # replayed by another chat
    await check(ada)
    assert state(await check(bob)) == {}  # and nobody else sees it
    assert (await link(ada)).status_code == 409  # already connected

    # a flow messages the linked chat: the graph names no recipient
    org = await org_of(client, ada)
    i, send, o = input_node("text"), tool_node("telegram_send"), output_node("r")
    flow = await make_flow(
        client, ada, [i, send, o],
        [edge(i, send, {"text": "{{text}}"}), edge(send, o, {"r": "{{status}}"})],
    )  # fmt: skip
    kit = tools.ToolKit(
        fetch=lambda url: None,  # type: ignore[arg-type,return-value]
        jobs=Provider(),
        mail=FakeEmailSender(),  # type: ignore[arg-type]
        chat=tg,
    )

    async def run(who, text: str) -> dict:
        r = await client.post(
            f"{BASE}/flows/{flow['id']}/runs",
            headers=who,
            json={"inputs": {"text": text}},
        )
        await engine.execute(
            db_session, fake_llm, org_id=org, run_id=UUID(r.json()["id"]), kit=kit
        )
        return (
            await client.get(f"{BASE}/flow-runs/{r.json()['id']}", headers=who)
        ).json()

    tg.sent.clear()
    done = await run(ada, "Your day: 9h standup")
    assert done["status"] == "done" and tg.sent == [(444, "Your day: 9h standup")]

    # the person blocks the bot: the step fails safely and the dead link is dropped
    tg.blocked.add(444)
    assert (await run(ada, "again"))["error_code"] == "connection_lost"
    assert state(await client.get(f"{BASE}/connections", headers=ada)) == {}
    assert (await run(ada, "once more"))["error_code"] == "not_connected"

    # disconnect: a pending link can be cancelled too
    await link(ada)
    assert (
        await client.delete(f"{BASE}/connections/telegram", headers=ada)
    ).status_code == 204
    assert (
        await client.delete(f"{BASE}/connections/telegram", headers=ada)
    ).status_code == 404
