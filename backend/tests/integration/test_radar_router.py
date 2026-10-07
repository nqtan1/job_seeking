"""/api/v1/radar through real HTTP (A-04): searches, queued runs, results actions, tenancy."""

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.prompts import fit
from recruitai.modules.jobs import repository as jobs_repo
from recruitai.modules.jobs.models import JobPosting
from recruitai.modules.jobs.schemas import UnifiedJobSearchResult
from recruitai.modules.jobs.service import to_job_position
from recruitai.modules.radar import repository
from tests.integration.test_matching_router import _add_profile
from tests.integration.test_radar_service import Provider, _fit

BASE = "/api/v1/radar"


@pytest.fixture
def ada(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-ada', 'ada@example.com')}"}


@pytest.fixture
def bob(emulator_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {emulator_token('uid-bob', 'bob@example.com')}"}


async def _org_id(client: httpx.AsyncClient, who):
    from uuid import UUID

    return UUID((await client.get("/api/v1/me", headers=who)).json()["active_org_id"])


async def test_searches_are_bounded_limited_to_three_and_private(
    client: httpx.AsyncClient, ada, bob
):
    made = await client.post(
        f"{BASE}/searches",
        headers=ada,
        json={"name": "Python Paris", "query": "python"},
    )
    assert made.status_code == 201
    search = made.json()
    assert (search["min_score"], search["daily_limit"], search["enabled"]) == (
        70,
        5,
        True,
    )

    assert (
        await client.post(
            f"{BASE}/searches", headers=ada, json={"name": "x", "min_score": 101}
        )
    ).status_code == 422
    for n in range(2):
        await client.post(f"{BASE}/searches", headers=ada, json={"name": f"r{n}"})
    fourth = await client.post(
        f"{BASE}/searches", headers=ada, json={"name": "too many"}
    )
    assert fourth.status_code == 422

    url = f"{BASE}/searches/{search['id']}"
    patched = await client.patch(
        url, headers=ada, json={"min_score": 80, "enabled": False}
    )
    assert (patched.json()["min_score"], patched.json()["enabled"]) == (80, False)
    assert (
        await client.patch(url, headers=ada, json={"name": None})
    ).status_code == 422
    # another user sees none of it
    assert (await client.get(f"{BASE}/searches", headers=bob)).json() == []
    assert (
        await client.patch(url, headers=bob, json={"name": "mine now"})
    ).status_code == 404
    assert (await client.delete(url, headers=bob)).status_code == 404
    assert (await client.post(f"{url}/run", headers=bob)).status_code == 404
    assert (await client.delete(url, headers=ada)).status_code == 204


async def test_run_now_is_queued_executed_by_the_worker_and_cannot_be_spammed(
    real_client: httpx.AsyncClient, task_app, fake_llm, users, monkeypatch
):
    ada, bob = users["ada"], users["bob"]
    monkeypatch.setattr(
        "recruitai.ai.dependencies.build_llm_gateway", lambda *a, **k: fake_llm
    )
    monkeypatch.setattr(
        "recruitai.modules.jobs.providers.factory.france_travail_provider",
        lambda: Provider(["A", "B"]),
    )
    await _add_profile(real_client, fake_llm, ada)
    search = (
        await real_client.post(
            f"{BASE}/searches",
            headers=ada,
            json={"name": "Py", "query": f"python-{uuid4().hex}"},
        )  # unique: the search cache is shared and this test commits
    ).json()
    for score in (85, 40):
        fake_llm.queue(fit.PROMPT_VERSION, _fit(score))

    accepted = await real_client.post(
        f"{BASE}/searches/{search['id']}/run", headers=ada
    )

    assert accepted.status_code == 202
    status_url = accepted.json()["status_url"]
    assert (await real_client.get(status_url, headers=ada)).json()["status"] == "queued"
    assert (await real_client.get(status_url, headers=bob)).status_code == 404

    await task_app.run_worker_async(wait=False, install_signal_handlers=False)

    assert (await real_client.get(status_url, headers=ada)).json()["status"] == "done"
    shortlist = (await real_client.get(f"{BASE}/results", headers=ada)).json()
    assert [(r["score"], r["title"]) for r in shortlist] == [(85.0, "Job A")]
    run = (await real_client.get(f"{BASE}/runs", headers=ada)).json()[0]
    assert (run["found"], run["scored"], run["shortlisted"], run["stop_reason"]) == (
        2,
        2,
        1,
        "done",
    )
    jobs = (await real_client.get("/api/v1/jobs", headers=ada)).json()
    assert [j["data"]["title"] for j in jobs] == [
        "Job A"
    ]  # the weak match left the inbox
    assert (await real_client.get(f"{BASE}/results", headers=bob)).json() == []
    # it just ran: another "Run now" is refused for a few minutes
    again = await real_client.post(f"{BASE}/searches/{search['id']}/run", headers=ada)
    assert again.status_code == 422


async def test_approve_keeps_the_job_dismiss_removes_it_and_results_are_private(
    client: httpx.AsyncClient, db_session: AsyncSession, ada, bob
):
    org = await _org_id(client, ada)
    search = await repository.create_search(
        db_session, org_id=org, values={"name": "Py"}
    )
    info = to_job_position(
        UnifiedJobSearchResult(
            id="E1", title="Dev", company="Acme", url="https://x.test"
        )
    )
    jobs = {}
    for ext in ("E1", "E2"):
        jobs[ext] = await jobs_repo.add(
            db_session, org_id=org, source="france_travail", external_id=ext, info=info
        )
        await repository.add_result(
            db_session,
            org_id=org,
            search_id=search.id,
            source="france_travail",
            external_id=ext,
            job_id=jobs[ext].id,
            score=80.0 if ext == "E1" else 90.0,
            status="new",
        )
    listed = (await client.get(f"{BASE}/results", headers=ada)).json()
    assert [(r["score"], r["title"], r["company"]) for r in listed] == [
        (90.0, "Dev", "Acme"),
        (80.0, "Dev", "Acme"),
    ]
    first, second = listed[1]["id"], listed[0]["id"]  # E1 (80), E2 (90)

    assert (
        await client.post(f"{BASE}/results/{first}/approve", headers=bob)
    ).status_code == 404
    assert (
        await client.post(f"{BASE}/results/{first}/approve", headers=ada)
    ).status_code == 204
    assert (
        await client.post(f"{BASE}/results/{second}/dismiss", headers=ada)
    ).status_code == 204

    assert (
        await client.get(f"{BASE}/results", headers=ada)
    ).json() == []  # none are "new" now
    approved = (await client.get(f"{BASE}/results?status=approved", headers=ada)).json()
    assert [r["id"] for r in approved] == [first]
    left = (await db_session.execute(select(JobPosting.external_id))).scalars().all()
    assert left == ["E1"]  # the dismissed job left the inbox, the approved one stayed
    assert (await client.get(f"{BASE}/results", headers=bob)).json() == []
    assert (await client.get(f"{BASE}/runs", headers=ada)).json() == []


async def test_kill_switch_stops_run_now_and_usage_shows_the_daily_cap(
    client: httpx.AsyncClient, app, ada
):
    from recruitai.config import get_settings

    search = (
        await client.post(f"{BASE}/searches", headers=ada, json={"name": "Py"})
    ).json()
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"radar_enabled": False, "ai_daily_quota_per_user": 50}
    )

    off = await client.post(f"{BASE}/searches/{search['id']}/run", headers=ada)
    usage = (await client.get(f"{BASE}/usage", headers=ada)).json()

    assert off.status_code == 503 and off.json()["code"] == "radar_disabled"
    assert usage == {"used": 0, "quota": 50, "radar_stops_at": 35}


async def test_skipped_results_are_not_actionable_and_dead_shortlist_entries_are_hidden(
    client: httpx.AsyncClient, db_session: AsyncSession, ada
):
    from sqlalchemy import text

    org = await _org_id(client, ada)
    search = await repository.create_search(
        db_session, org_id=org, values={"name": "Py"}
    )
    info = to_job_position(
        UnifiedJobSearchResult(
            id="K1", title="Kept", company="Acme", url="https://x.test"
        )
    )
    kept = await jobs_repo.add(
        db_session, org_id=org, source="france_travail", external_id="K1", info=info
    )
    for ext, job_id, status in (
        ("K1", kept.id, "new"),
        ("S1", None, "skipped"),
        ("D1", None, "new"),
    ):
        await repository.add_result(
            db_session,
            org_id=org,
            search_id=search.id,
            source="france_travail",
            external_id=ext,
            job_id=job_id,
            score=50.0,
            status=status,
        )

    listed = (await client.get(f"{BASE}/results", headers=ada)).json()
    assert [r["title"] for r in listed] == [
        "Kept"
    ]  # D1's job is gone, S1 was never shortlisted
    skipped = (
        await db_session.execute(
            text("SELECT id FROM radar_results WHERE status = 'skipped'")
        )
    ).scalar_one()
    assert (
        await client.post(f"{BASE}/results/{skipped}/approve", headers=ada)
    ).status_code == 404
    assert (
        await client.post(f"{BASE}/results/{skipped}/dismiss", headers=ada)
    ).status_code == 404


async def test_status_insights_and_review_anyway_over_http(
    client: httpx.AsyncClient, app, db_session: AsyncSession, ada, bob
):
    org = await _org_id(client, ada)
    empty = (await client.get(f"{BASE}/status", headers=ada)).json()
    assert (
        empty["new_matches"],
        empty["searches"],
        empty["running"],
        empty["next_run_at"],
    ) == (0, 0, False, None)

    search = await repository.create_search(
        db_session, org_id=org, values={"name": "Py"}
    )
    info = to_job_position(
        UnifiedJobSearchResult(
            id="N1", title="Dev", company="Acme", url="https://x.test"
        )
    )
    job = await jobs_repo.add(
        db_session, org_id=org, source="france_travail", external_id="N1", info=info
    )
    await repository.add_result(
        db_session,
        org_id=org,
        search_id=search.id,
        source="france_travail",
        external_id="N1",
        job_id=job.id,
        score=88.0,
        status="new",
        title="Dev",
        company="Acme",
        highlights={
            "strengths": ["Python"],
            "gaps": ["No cloud"],
            "missing": ["AWS"],
            "summary": None,
        },
    )
    await repository.add_result(
        db_session,
        org_id=org,
        search_id=search.id,
        source="france_travail",
        external_id="N2",
        job_id=None,
        score=40.0,
        status="skipped",
        title="Weak",
        company="Corp",
        highlights={"missing": ["AWS"]},
    )

    status = (await client.get(f"{BASE}/status", headers=ada)).json()
    assert (status["new_matches"], status["searches"], status["daily_searches"]) == (
        1,
        1,
        1,
    )
    assert status["next_run_at"] is not None
    card = (await client.get(f"{BASE}/results", headers=ada)).json()[0]
    assert (
        card["search_name"],
        card["highlights"]["strengths"],
        card["application_status"],
    ) == ("Py", ["Python"], None)
    rejected = (await client.get(f"{BASE}/results?status=skipped", headers=ada)).json()
    assert [(r["title"], r["highlights"]["missing"]) for r in rejected] == [
        ("Weak", ["AWS"])
    ]
    funnel = (await client.get(f"{BASE}/insights", headers=ada)).json()
    assert funnel["funnel"]["scored"] == 2 and funnel["funnel"]["shortlisted"] == 1
    assert (await client.get(f"{BASE}/status", headers=bob)).json()["new_matches"] == 0

    from recruitai.modules.radar.router import get_provider

    app.dependency_overrides[get_provider] = lambda: Provider(["N2"])
    kept = await client.post(f"{BASE}/results/{rejected[0]['id']}/keep", headers=ada)
    assert kept.status_code == 200 and kept.json()["job_id"]
    assert (
        await client.post(f"{BASE}/results/{rejected[0]['id']}/keep", headers=bob)
    ).status_code == 404
    again = await client.post(f"{BASE}/results/{rejected[0]['id']}/keep", headers=ada)
    assert again.status_code == 404  # no longer a rejected result
