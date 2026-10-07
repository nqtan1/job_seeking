"""Walkthrough §5 end to end (P2-21): letter → POST /render (202) → worker → poll → signed URL.

The worker runs on its own connection, so this test uses real commits (not the rolled-back
``db_session``) and deletes what it created. Only the compiler is faked; the real Tectonic
runs in the worker-image check."""

from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.letters import PROMPT_VERSION
from recruitai.core.storage import LocalStorage
from recruitai.core.tasks import TaskRun
from recruitai.modules.letters import tasks
from tests.integration.test_letters_service import DRAFT
from tests.integration.test_matching_router import _add_job, _add_profile

PDF = b"%PDF-1.4 rendered letter"


async def test_render_request_poll_and_download(
    real_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    task_app,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    users,
    monkeypatch,
):
    ada, bob = users["ada"], users["bob"]

    async def fake_compile(tex: str) -> bytes:
        return PDF

    monkeypatch.setattr(tasks, "compile_tex", fake_compile)
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)

    await _add_profile(real_client, fake_llm, ada)
    job_id = await _add_job(real_client, fake_llm, ada)
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    letter = (
        await real_client.post("/api/v1/letters", headers=ada, json={"job_id": job_id})
    ).json()
    base = f"/api/v1/letters/{letter['id']}"
    assert letter["render_status"] == "none" and letter["pdf_document_id"] is None

    # another org cannot trigger a render of this letter, and nothing is queued by trying
    assert (await real_client.post(f"{base}/render", headers=bob)).status_code == 404
    assert (await real_client.get(base, headers=ada)).json()["render_status"] == "none"
    unknown = f"/api/v1/letters/{uuid4()}/render"
    assert (await real_client.post(unknown, headers=ada)).status_code == 404

    accepted = await real_client.post(f"{base}/render", headers=ada)
    assert accepted.status_code == 202
    task_id, status_url = accepted.json()["task_id"], accepted.json()["status_url"]
    assert status_url == f"/api/v1/tasks/{task_id}"
    assert (await real_client.get(base, headers=ada)).json()[
        "render_status"
    ] == "queued"
    queued = (await real_client.get(status_url, headers=ada)).json()
    assert (queued["status"], queued["download_url"]) == ("queued", None)
    assert (
        await real_client.get(status_url, headers=bob)
    ).status_code == 404  # not Bob's task

    await task_app.run_worker_async(wait=False, install_signal_handlers=False)

    done = (await real_client.get(status_url, headers=ada)).json()
    assert done["status"] == "done" and done["error_code"] is None
    assert "exp=" in done["download_url"] and "sig=" in done["download_url"]
    assert (await real_client.get(status_url, headers=bob)).status_code == 404
    final = (await real_client.get(base, headers=ada)).json()
    assert (
        final["render_status"] == "done"
        and final["pdf_document_id"] == done["result_ref"]
    )

    downloaded = await real_client.get(done["download_url"])
    assert downloaded.status_code == 200 and downloaded.content == PDF

    # Defense in depth beyond the link's own expiry: the link works for a plain browser fetch
    # and for its owner, but another org's *authenticated* request for it is a 404.
    assert (await real_client.get(done["download_url"], headers=ada)).content == PDF
    assert (await real_client.get(done["download_url"], headers=bob)).status_code == 404

    # A task of Bob's whose result points at Ada's PDF must not hand Bob a link to it.
    bob_org = (await real_client.get("/api/v1/me", headers=bob)).json()["active_org_id"]
    poisoned_id = uuid4()
    async with AsyncSession(db_engine) as session:
        poisoned = TaskRun(
            id=poisoned_id,
            org_id=UUID(bob_org),
            kind="letters.render_pdf",
            status="done",
            result_ref=done["result_ref"],
        )
        session.add(poisoned)
        await session.commit()
    seen = (await real_client.get(f"/api/v1/tasks/{poisoned_id}", headers=bob)).json()
    assert seen["status"] == "done" and seen["download_url"] is None
