"""Connection and recipient abuse paths: link phishing, racing polls, the opt-out oracle."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from recruitai.core.email import FakeEmailSender
from recruitai.core.telegram import FakeTelegram, Update
from recruitai.modules.agents.connections.models import Connection
from recruitai.modules.agents.connections.router import bot
from recruitai.modules.agents.contacts import repository as rrepo
from recruitai.modules.agents.contacts import service as recipients
from recruitai.modules.agents.contacts.router import get_sender
from tests.integration.test_flows import BASE, org_of


async def test_a_linked_chat_is_told_who_and_can_undo_it_and_one_chat_has_one_owner(
    client, app, db_session, ada, bob
):
    tg = FakeTelegram()
    app.dependency_overrides[bot] = lambda: tg
    check = lambda who: client.post(f"{BASE}/connections/telegram/check", headers=who)
    started = await client.post(f"{BASE}/connections/telegram/link", headers=ada)
    tg.inbox.append(Update(1, 444, f"/start {started.json()['url'].split('=')[1]}"))
    await check(ada)
    welcome = tg.sent[-1][1]
    assert "/stop" in welcome and "ada@example.com" not in welcome  # masked or absent

    tg.inbox.append(Update(2, 999, "/stop"))  # a chat that was never linked: no answer
    await check(ada)
    assert len(tg.sent) == 1
    tg.inbox.append(Update(3, 444, "/stop"))
    await check(ada)
    assert tg.sent[-1] == (444, "Disconnected.")
    listed = (await client.get(f"{BASE}/connections", headers=ada)).json()["items"]
    assert [c for c in listed if c["status"] == "active"] == []

    # the database refuses a second owner for one chat, whatever the polls do
    own = lambda org, user: Connection(
        org_id=org, user_id=UUID(user), provider="telegram", status="active", chat_id=7
    )
    for who in (ada, bob):
        user = (await client.get(f"{BASE}/me", headers=who)).json()["user"]["id"]
        db_session.add(own(await org_of(client, who), user))
        if who is ada:
            await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_an_opted_out_address_hits_the_same_limits_as_any_other(
    client, app, db_session, ada
):
    app.dependency_overrides[get_sender] = lambda: FakeEmailSender()
    out, normal = "gone@example.com", "here@example.com"
    await rrepo.suppress_everywhere(
        db_session, email=out, email_hash=recipients.email_hash(out)
    )
    me = (await client.get(f"{BASE}/me", headers=ada)).json()["user"]
    for email in (out, normal):
        for _ in range(recipients.MAX_INVITES_PER_ADDRESS_DAY):
            await rrepo.add_invite(
                db_session, user_id=me["id"], email_hash=recipients.email_hash(email)
            )
    await db_session.commit()
    codes = [
        (
            await client.post(
                f"{BASE}/email-recipients", headers=ada, json={"email": e}
            )
        ).status_code
        for e in (out, normal)
    ]
    assert codes == [409, 409]


async def test_a_parallel_poll_that_lost_the_race_skips_the_link_and_the_session_stays_usable(
    client, app, db_session, ada, bob, monkeypatch
):
    """Both polls saw the chat as free; the database constraint decides, the loser is skipped."""
    from recruitai.modules.agents.connections import repository as repo
    from recruitai.modules.agents.connections import service as connections

    tg = FakeTelegram()
    app.dependency_overrides[bot] = lambda: tg
    codes = []
    for who in (ada, bob):
        r = await client.post(f"{BASE}/connections/telegram/link", headers=who)
        codes.append(r.json()["url"].split("?start=")[1])
    tg.inbox += [Update(1, 777, f"/start {codes[0]}")]
    assert await connections.poll_telegram(db_session, tg, now=datetime.now(UTC)) == 1

    async def free(
        *a, **k
    ):  # the race: the second poll's check ran before the first committed
        return False

    monkeypatch.setattr(repo, "chat_is_linked", free)
    tg.inbox += [Update(2, 777, f"/start {codes[1]}")]
    assert await connections.poll_telegram(db_session, tg, now=datetime.now(UTC)) == 0
    assert (
        await db_session.execute(text("SELECT 1"))
    ).scalar() == 1  # session still usable
