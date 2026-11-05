"""Outside effects (send_email, telegram_send): a Resume never repeats one that happened, and never
loses one that did not."""

from uuid import UUID

import httpx
from sqlalchemy import text

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.email import FakeEmailSender
from recruitai.core.errors import UpstreamUnavailable
from recruitai.core.telegram import FakeTelegram, TelegramError, Update
from recruitai.modules.agents.blocks import tools
from recruitai.modules.agents.connections.router import bot
from recruitai.modules.agents.contacts.router import get_sender
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


async def _flow(client, who, kind: str, mapping: dict[str, str]):
    i, send, o = input_node("x"), tool_node(kind), output_node("r")
    flow = await make_flow(
        client, who, [i, send, o],
        [edge(i, send, mapping), edge(send, o, {"r": "{{status}}"})],
    )  # fmt: skip
    return flow, send


async def test_a_resume_does_not_repeat_a_done_effect_nor_lose_one_that_never_left(
    client, app, db_session, fake_llm: FakeLLMGateway, task_app, ada, monkeypatch
):
    org = await org_of(client, ada)
    tg, mail = FakeTelegram(), FakeEmailSender()
    app.dependency_overrides[bot] = lambda: tg
    app.dependency_overrides[get_sender] = lambda: mail
    kit = tools.ToolKit(
        fetch=lambda url: None,  # type: ignore[arg-type,return-value]
        jobs=Provider(),
        mail=mail,
        chat=tg,
    )

    async def execute(run_id: str) -> dict:
        await engine.execute(
            db_session, fake_llm, org_id=org, run_id=UUID(run_id), kit=kit
        )
        return (await client.get(f"{BASE}/flow-runs/{run_id}", headers=ada)).json()

    async def start(flow) -> str:
        r = await client.post(
            f"{BASE}/flows/{flow['id']}/runs",
            headers=ada,
            json={"inputs": {"x": "a@b.co"}},
        )
        return r.json()["id"]

    async def resume(run_id: str) -> dict:
        assert (
            await client.post(f"{BASE}/flow-runs/{run_id}/resume", headers=ada)
        ).status_code == 202
        return await execute(run_id)

    # link a chat, confirm an address
    code = (
        (await client.post(f"{BASE}/connections/telegram/link", headers=ada))
        .json()["url"]
        .split("?start=")[1]
    )
    tg.inbox.append(Update(1, 444, f"/start {code}"))
    await client.post(f"{BASE}/connections/telegram/check", headers=ada)
    tg.sent.clear()
    await client.post(f"{BASE}/email-recipients", headers=ada, json={"email": "a@b.co"})
    link = mail.sent[-1].context["link"].split("/api/public", 1)[1]
    await client.post("/api/public" + link)
    mail.sent.clear()

    # 1. the effect already happened (a worker died after sending): Resume finishes, sends nothing
    flow, send = await _flow(client, ada, "telegram_send", {"text": "{{x}}"})
    rid = await start(flow)
    await db_session.execute(
        text(
            "INSERT INTO flow_effects (id, org_id, user_id, run_id, node_id, kind)"
            " SELECT gen_random_uuid(), org_id, user_id, id, :n, 'telegram_send'"
            " FROM flow_runs WHERE id = :r"
        ),
        {"n": UUID(send["id"]), "r": UUID(rid)},
    )
    await db_session.commit()
    done = await execute(rid)
    step = next(s for s in done["steps"] if s["node_id"] == send["id"])
    assert done["status"] == "done" and step["output"] == {"status": "already done"}
    assert tg.sent == []

    # 2. Telegram: outcome unknown (read timeout) keeps the slot; a refusal gives it back
    flow, send = await _flow(client, ada, "telegram_send", {"text": "{{x}}"})
    real = tg.send

    async def timeout(chat_id, text):
        raise TelegramError(unknown=True)

    async def refused(chat_id, text):
        raise TelegramError()

    monkeypatch.setattr(tg, "send", timeout)
    rid = await start(flow)
    failed = await execute(rid)
    assert failed["error_code"] == "delivery_unknown"
    monkeypatch.setattr(tg, "send", real)
    assert (await resume(rid))["status"] == "done"
    assert tg.sent == []  # at most once: the unknown one is never sent again

    monkeypatch.setattr(tg, "send", refused)
    rid = await start(flow)
    assert (await execute(rid))["error_code"] == "tool_failed"
    monkeypatch.setattr(tg, "send", real)
    assert (await resume(rid))["status"] == "done"
    assert tg.sent == [(444, "a@b.co")]

    # 3. the same for email: only a timeout after the request left is unknown
    flow, send = await _flow(
        client, ada, "send_email", {"to": "{{x}}", "subject": "Hi", "body": "Note"}
    )
    real_send = mail.send

    def down(cause: Exception):
        async def send_(*a, **k):
            raise UpstreamUnavailable("x", code="email_unavailable") from cause

        return send_

    req = httpx.Request("POST", "https://x")
    monkeypatch.setattr(mail, "send", down(httpx.ReadTimeout("t", request=req)))
    rid = await start(flow)
    assert (await execute(rid))["error_code"] == "delivery_unknown"
    monkeypatch.setattr(mail, "send", real_send)
    assert (await resume(rid))["status"] == "done" and mail.sent == []

    monkeypatch.setattr(mail, "send", down(httpx.ConnectError("c", request=req)))
    rid = await start(flow)
    assert (await execute(rid))["error_code"] == "email_unavailable"
    monkeypatch.setattr(mail, "send", real_send)
    assert (await resume(rid))["status"] == "done" and len(mail.sent) == 1
