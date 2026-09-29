import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.auth import _API_KEY, _BASE, _host


async def test_db_session_is_a_working_transaction_even_when_the_code_commits(
    db_session: AsyncSession,
):
    await db_session.execute(text("CREATE TABLE harness_probe (n int)"))
    await db_session.execute(text("INSERT INTO harness_probe VALUES (1)"))
    await (
        db_session.commit()
    )  # only a savepoint; the outer transaction is rolled back at teardown

    assert (
        await db_session.execute(text("SELECT count(*) FROM harness_probe"))
    ).scalar() == 1


async def test_app_fixture_serves_health_and_uses_the_overridden_db(
    client: httpx.AsyncClient,
):
    assert (await client.get("/health")).json() == {"status": "ok"}
    assert (await client.get("/ready")).json() == {"status": "ready"}


def test_emulator_tokens_are_accepted_by_the_emulator_and_distinct(
    emulator_token, two_tenant_tokens
):
    token = emulator_token("uid-harness-1", "harness1@example.test")
    resp = httpx.post(
        f"http://{_host()}/{_BASE}/accounts:lookup",
        params={"key": _API_KEY},
        json={"idToken": token},
        timeout=10,
    )
    assert (
        resp.status_code == 200
        and resp.json()["users"][0]["email"] == "harness1@example.test"
    )

    a, b = two_tenant_tokens
    assert a != b
