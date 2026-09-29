import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.auth import _API_KEY, _BASE, _host


async def test_db_session_writes_inside_transaction(db_session: AsyncSession):
    await db_session.execute(text("CREATE TABLE harness_probe (n int)"))
    await db_session.execute(text("INSERT INTO harness_probe VALUES (1)"))
    await db_session.commit()  # savepoint only; must still roll back at teardown

    assert (
        await db_session.execute(text("SELECT count(*) FROM harness_probe"))
    ).scalar() == 1


async def test_db_session_rolled_back_between_tests(db_session: AsyncSession):
    found = await db_session.execute(text("SELECT to_regclass('harness_probe')"))

    assert found.scalar() is None


async def test_app_fixture_serves_health(client: httpx.AsyncClient):
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_app_fixture_overrides_db(client: httpx.AsyncClient):
    resp = await client.get("/ready")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_emulator_token_is_accepted_by_emulator(emulator_token):
    token = emulator_token("uid-harness-1", "harness1@example.test")

    resp = httpx.post(
        f"http://{_host()}/{_BASE}/accounts:lookup",
        params={"key": _API_KEY},
        json={"idToken": token},
        timeout=10,
    )

    assert resp.status_code == 200
    assert resp.json()["users"][0]["email"] == "harness1@example.test"


def test_two_tenant_tokens_are_distinct(two_tenant_tokens):
    a, b = two_tenant_tokens

    assert a != b
