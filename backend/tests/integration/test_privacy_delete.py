"""Account deletion (P2-30): rows, queued jobs, files and the Firebase identity are all gone;
nobody else's data is touched; a revoked token is refused; a fresh sign-in starts empty."""

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import firebase_admin
import httpx
import pytest
from firebase_admin import auth as firebase_auth
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts import coach as coach_prompt
from recruitai.ai.prompts import fit as fit_prompt
from recruitai.ai.prompts import letters as letters_prompt
from recruitai.core.storage import LocalStorage, ObjectNotFound
from recruitai.modules.matching.schemas import FitCheck
from tests.fixtures.auth import mint_emulator_token
from tests.integration.test_letters_service import DRAFT
from tests.integration.test_matching_router import _add_job, _add_profile
from tests.unit.test_schemas import VALID

ORG_TABLES = (
    "memberships", "documents", "ai_calls", "task_runs", "candidate_profiles",
    "job_postings", "fit_analyses", "letters", "letter_versions", "applications",
    "application_events", "conversations", "messages", "radar_searches", "radar_results",
    "radar_runs",
)  # fmt: skip


@pytest.fixture
async def accounts(db_engine: AsyncEngine) -> AsyncIterator[dict[str, dict[str, str]]]:
    tag = uuid4().hex[:8]
    people = {
        name: {"uid": f"uid-{name}-{tag}", "email": f"{name}-{tag}@example.com"}
        for name in ("ada", "bob", "carol")
    }
    for person in people.values():
        person["token"] = mint_emulator_token(person["uid"], person["email"])
        person["Authorization"] = f"Bearer {person['token']}"
    yield people
    async with db_engine.begin() as conn:  # whatever the test left behind
        for person in people.values():
            await conn.execute(
                text(
                    "DELETE FROM organizations WHERE id IN (SELECT m.org_id FROM memberships m"
                    " JOIN users u ON u.id = m.user_id WHERE u.firebase_uid = :u)"
                ),
                {"u": person["uid"]},
            )
            await conn.execute(
                text("DELETE FROM users WHERE firebase_uid = :u"), {"u": person["uid"]}
            )
    app = firebase_admin.get_app()
    for person in people.values():
        try:
            firebase_auth.delete_user(person["uid"], app=app)
        except firebase_auth.UserNotFoundError:
            pass


async def _purge_uid(db_engine: AsyncEngine, uid: str) -> None:
    """Remove an identity's rows (org first: it cascades) and its Firebase user."""
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM organizations WHERE id IN (SELECT m.org_id FROM memberships m"
                " JOIN users u ON u.id = m.user_id WHERE u.firebase_uid = :u)"
            ),
            {"u": uid},
        )
        await conn.execute(
            text("DELETE FROM users WHERE firebase_uid = :u"), {"u": uid}
        )
    try:
        firebase_auth.delete_user(uid, app=firebase_admin.get_app())
    except firebase_auth.UserNotFoundError:
        pass


def _auth(person: dict[str, str]) -> dict[str, str]:
    return {"Authorization": person["Authorization"]}


async def _fill_account(
    client: httpx.AsyncClient, llm: FakeLLMGateway, db_engine: AsyncEngine, person
) -> tuple[str, str]:
    """Data in every module, a stored file, a queued export job and an ai_calls row.
    Returns (org_id, user_id)."""
    headers = _auth(person)
    await _add_profile(client, llm, headers)  # profile + its CV document
    job_id = await _add_job(client, llm, headers)
    llm.queue(fit_prompt.PROMPT_VERSION, FitCheck.model_validate(VALID))
    await client.post("/api/v1/fit-analyses", headers=headers, json={"job_id": job_id})
    llm.queue(letters_prompt.PROMPT_VERSION, DRAFT)
    await client.post("/api/v1/letters", headers=headers, json={"job_id": job_id})
    await client.post("/api/v1/applications", headers=headers, json={"job_id": job_id})
    conversation = (
        await client.post("/api/v1/coach/conversations", headers=headers, json={})
    ).json()
    llm.queue_stream(coach_prompt.PROMPT_VERSION, ["Bonjour"])
    await client.post(
        f"/api/v1/coach/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"content": "Salut"},
    )
    assert (
        await client.post("/api/v1/me/export", headers=headers)
    ).status_code == 202  # queued job
    me = (await client.get("/api/v1/me", headers=headers)).json()
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ai_calls (id, org_id, user_id, feature, model, prompt_version,"
                " latency_ms, status) VALUES (:i, :o, :u, 'f', 'm', 'f@1', 1, 'ok')"
            ),
            {"i": uuid4(), "o": me["active_org_id"], "u": me["user"]["id"]},
        )
        search_id = uuid4()
        org = {"o": me["active_org_id"], "s": search_id}
        await conn.execute(
            text("INSERT INTO radar_searches (id, org_id, name) VALUES (:s, :o, 'Py')"),
            org,
        )
        await conn.execute(
            text(
                "INSERT INTO radar_results (id, org_id, search_id, source, external_id)"
                " VALUES (gen_random_uuid(), :o, :s, 'ft', 'X')"
            ),
            org,
        )
        await conn.execute(
            text(
                "INSERT INTO radar_runs (id, org_id, search_id) VALUES (gen_random_uuid(), :o, :s)"
            ),
            org,
        )
    return me["active_org_id"], me["user"]["id"]


async def _rows(db_engine: AsyncEngine, org_id: str, user_id: str) -> dict[str, int]:
    counts = {}
    async with db_engine.connect() as conn:
        for table in ORG_TABLES:
            counts[table] = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE org_id = :o"),
                    {"o": org_id},
                )
            ).scalar_one()
        # org_id-less tables: child rows of a letter / application / conversation carry org_id too
        counts["organizations"] = (
            await conn.execute(
                text("SELECT count(*) FROM organizations WHERE id = :o"), {"o": org_id}
            )
        ).scalar_one()
        counts["users"] = (
            await conn.execute(
                text("SELECT count(*) FROM users WHERE id = :u"), {"u": user_id}
            )
        ).scalar_one()
        counts["procrastinate_jobs"] = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM procrastinate_jobs WHERE args->>'org_id' = :o"
                ),
                {"o": org_id},
            )
        ).scalar_one()
    return counts


async def _storage_keys(db_engine: AsyncEngine, org_id: str) -> list[str]:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT storage_key FROM documents WHERE org_id = :o"), {"o": org_id}
        )
        return [r[0] for r in rows]


async def test_delete_removes_everything_of_the_caller_and_nothing_of_anyone_else(
    real_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    task_app,  # applies the Procrastinate schema (queued-job cleanup is part of the deal)
    accounts,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
):
    ada, bob = accounts["ada"], accounts["bob"]
    ada_org, ada_user = await _fill_account(real_client, fake_llm, db_engine, ada)
    bob_org, bob_user = await _fill_account(real_client, fake_llm, db_engine, bob)
    ada_files = await _storage_keys(db_engine, ada_org)
    bob_files = await _storage_keys(db_engine, bob_org)
    before_ada = await _rows(db_engine, ada_org, ada_user)
    before_bob = await _rows(db_engine, bob_org, bob_user)
    assert ada_files and bob_files and before_ada["procrastinate_jobs"] == 1
    assert all(n > 0 for n in before_ada.values()), before_ada  # data in every table

    resp = await real_client.delete("/api/v1/me", headers=_auth(ada))
    assert resp.status_code == 204

    after_ada = await _rows(db_engine, ada_org, ada_user)
    assert all(n == 0 for n in after_ada.values()), (
        after_ada
    )  # DB, task_runs, ai_calls, queue
    for key in ada_files:
        with pytest.raises(ObjectNotFound):
            await fake_storage.get(key)
    with pytest.raises(
        firebase_auth.UserNotFoundError
    ):  # the sign-in identity is gone too
        firebase_auth.get_user(ada["uid"], app=firebase_admin.get_app())

    assert await _rows(db_engine, bob_org, bob_user) == before_bob  # org B is untouched
    for key in bob_files:
        assert await fake_storage.get(key)
    assert (
        firebase_auth.get_user(bob["uid"], app=firebase_admin.get_app()).email
        == bob["email"]
    )
    assert (
        await real_client.get("/api/v1/profile", headers=_auth(bob))
    ).status_code == 200


async def test_the_old_token_cannot_delete_again_and_a_fresh_sign_in_starts_empty(
    real_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    task_app,
    accounts,
    fake_llm: FakeLLMGateway,
):
    ada = accounts["ada"]
    old_org, old_user = await _fill_account(real_client, fake_llm, db_engine, ada)
    assert (
        await real_client.delete("/api/v1/me", headers=_auth(ada))
    ).status_code == 204

    # the deleted account's token is refused where it matters (revocation is checked here)
    assert (
        await real_client.delete("/api/v1/me", headers=_auth(ada))
    ).status_code == 401

    try:
        # the same person signing up again: new identity, same email, nothing carried over
        again = {
            "Authorization": f"Bearer {mint_emulator_token(ada['uid'] + '-again', ada['email'])}"
        }
        me = (await real_client.get("/api/v1/me", headers=again)).json()
        assert me["active_org_id"] != old_org and me["user"]["id"] != old_user
        assert (
            await real_client.get("/api/v1/profile", headers=again)
        ).status_code == 404
        assert (await real_client.get("/api/v1/jobs", headers=again)).json() == []
        assert (await real_client.get("/api/v1/letters", headers=again)).json() == []
        assert (
            await real_client.get("/api/v1/applications", headers=again)
        ).json() == []
    finally:
        await _purge_uid(db_engine, ada["uid"] + "-again")


async def test_a_revoked_token_is_refused_and_nothing_is_deleted(
    real_client: httpx.AsyncClient, db_engine: AsyncEngine, accounts
):
    carol = accounts["carol"]
    me = (
        await real_client.get("/api/v1/me", headers=_auth(carol))
    ).json()  # provisions her
    await asyncio.sleep(
        1.1
    )  # revocation has one-second granularity: the token must be older
    firebase_auth.revoke_refresh_tokens(carol["uid"], app=firebase_admin.get_app())

    # ordinary endpoints do not check revocation (an ID token lives up to an hour)...
    assert (
        await real_client.get("/api/v1/me", headers=_auth(carol))
    ).status_code == 200
    # ...but the destructive one does
    assert (
        await real_client.delete("/api/v1/me", headers=_auth(carol))
    ).status_code == 401
    assert (
        await real_client.post("/api/v1/me/export", headers=_auth(carol))
    ).status_code == 401  # the export too
    assert (await _rows(db_engine, me["active_org_id"], me["user"]["id"]))["users"] == 1
    assert firebase_auth.get_user(
        carol["uid"], app=firebase_admin.get_app()
    )  # identity intact
    assert (
        await real_client.delete("/api/v1/me")
    ).status_code == 401  # no token at all
