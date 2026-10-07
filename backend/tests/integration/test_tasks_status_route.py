"""GET /api/v1/tasks/{id} (P1-14): reads task_runs, org-scoped."""

from uuid import UUID

import httpx
from sqlalchemy import update

from recruitai.core.tasks import TaskRun, enqueue
from recruitai.worker import dummy


async def _enqueue_dummy(db_session, org_id: UUID) -> str:
    task_run_id = await enqueue(db_session, task=dummy, org_id=org_id, kind="dummy")
    await db_session.commit()
    return str(task_run_id)


async def _active_org_id(client: httpx.AsyncClient, token: str) -> UUID:
    resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    return UUID(resp.json()["active_org_id"])


async def test_polling_reports_queued_then_done(
    client: httpx.AsyncClient, emulator_token, db_session, task_app
):
    """The dummy task itself is exercised end to end (with a real worker) in
    tests/integration/test_core_tasks.py; here the concern is the *route*: it reads
    task_runs correctly regardless of what actually flips the status, so setting it
    directly keeps this test fast and focused on the route alone. ``task_app`` is unused
    directly but required: it's what applies Procrastinate's own schema to this test
    database — without it, ``enqueue()``'s ``defer_async`` fails with a raw connector error
    (no ``procrastinate_jobs`` table yet), same as any test that calls ``enqueue()``."""
    token = emulator_token("uid-taskroute-1", "taskroute1@example.test")
    org_id = await _active_org_id(client, token)
    task_run_id = await _enqueue_dummy(db_session, org_id)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/tasks/{task_run_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "queued",
        "result_ref": None,
        "error_code": None,
        "download_url": None,
    }

    await db_session.execute(
        update(TaskRun)
        .where(TaskRun.id == UUID(task_run_id))
        .values(status="done", result_ref="orgs/x/letter_pdf/y")
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/tasks/{task_run_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "done",
        "result_ref": "orgs/x/letter_pdf/y",  # not a document id: no download link
        "error_code": None,
        "download_url": None,
    }


async def test_cross_tenant_polling_is_404(
    client: httpx.AsyncClient, two_tenant_tokens, db_session, task_app
):
    token_a, token_b = two_tenant_tokens
    org_a = await _active_org_id(client, token_a)
    await _active_org_id(client, token_b)  # provisions org B, unused otherwise
    task_run_id = await _enqueue_dummy(db_session, org_a)

    resp = await client.get(
        f"/api/v1/tasks/{task_run_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert resp.status_code == 404
