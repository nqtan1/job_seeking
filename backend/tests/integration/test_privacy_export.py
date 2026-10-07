"""Data export (P2-29): the ZIP holds exactly the caller's data, from every module."""

import io
import json
import zipfile
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.storage import LocalStorage
from recruitai.modules.documents.models import Document
from recruitai.modules.privacy import service
from recruitai.modules.privacy import (
    tasks as privacy_tasks,  # noqa: F401  (registers the task)
)
from tests.fixtures.org_data import seed_org


async def _export_zip(
    db: AsyncSession, storage: LocalStorage, data, *, org_id: UUID | None = None
) -> zipfile.ZipFile:
    document_id = await service.build_export(
        db, storage, org_id=org_id or data.org_id, user_id=data.user.id
    )
    await db.commit()
    document = await db.get(Document, document_id)
    assert document is not None and (document.kind, document.mime) == (
        "export",
        "application/zip",
    )
    return zipfile.ZipFile(io.BytesIO(await storage.get(document.storage_key)))


def _all_text(archive: zipfile.ZipFile) -> str:
    return "\n".join(
        archive.read(n).decode("utf-8", errors="ignore") for n in archive.namelist()
    )


async def test_the_zip_has_every_module_and_the_original_files(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    a = await seed_org(db_session, "alpha", llm=fake_llm, storage=fake_storage)

    archive = await _export_zip(db_session, fake_storage, a)

    names = set(archive.namelist())
    assert {
        "account.json", "profile.json", "jobs.json", "fit_analyses.json", "letters.json",
        "letter_versions.json", "applications.json", "application_events.json",
        "coach_conversations.json", "coach_messages.json", "documents.json", "ai_usage.json",
        "radar_searches.json", "radar_results.json", "radar_runs.json", "manifest.json",
    } <= names  # fmt: skip
    read = lambda n: json.loads(archive.read(n))
    assert read("account.json")["user"]["email"] == "alpha@example.test"
    assert read("profile.json")[0]["name"] == "Lucas Martel"
    assert read("fit_analyses.json")[0]["data"]["summary"] == "fit-alpha"
    assert len(read("letter_versions.json")) == 2  # generated + the edit
    assert read("letters.json")[0]["content"]["opening"] == "edited-alpha"
    assert read("applications.json")[0]["notes"] == "notes-alpha"
    assert len(read("application_events.json")) == 1
    messages = read("coach_messages.json")
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "coach-question-alpha"), ("assistant", "coach-answer-alpha"),
    ]  # fmt: skip
    assert read("ai_usage.json")[0]["output_tokens"] == 7

    files = {n: archive.read(n) for n in names if n.startswith("files/")}
    assert sorted(files.values()) == [b"%PDF-1.4 cv-alpha", b"jd text alpha"]
    assert any(n.startswith("files/cv/") and n.endswith(".pdf") for n in files)
    manifest = read("manifest.json")
    assert manifest["counts"]["coach_messages"] == 2 and manifest["missing_files"] == []


async def test_one_orgs_export_never_contains_another_orgs_data(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    a = await seed_org(db_session, "alpha", llm=fake_llm, storage=fake_storage)
    b = await seed_org(db_session, "bravo", llm=fake_llm, storage=fake_storage)

    text_a = _all_text(await _export_zip(db_session, fake_storage, a))
    text_b = _all_text(await _export_zip(db_session, fake_storage, b))

    for marker in ("alpha", "bravo"):
        assert (marker in text_a) == (marker == "alpha")
        assert (marker in text_b) == (marker == "bravo")
    assert str(b.org_id) not in text_a and str(a.org_id) not in text_b


async def test_a_new_export_replaces_the_previous_one_and_missing_files_are_recorded(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    a = await seed_org(db_session, "alpha", llm=fake_llm, storage=fake_storage)
    await fake_storage.delete(a.document_keys[0])  # an object lost from storage

    await _export_zip(db_session, fake_storage, a)
    second = await _export_zip(db_session, fake_storage, a)

    from sqlalchemy import select

    exports = (
        (
            await db_session.execute(
                select(Document).where(
                    Document.kind == "export", Document.org_id == a.org_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(exports) == 1  # replaced, not accumulated
    manifest = json.loads(second.read("manifest.json"))
    assert len(manifest["missing_files"]) == 1  # recorded, the export did not fail
    assert not any(
        n.startswith("files/export") for n in second.namelist()
    )  # no zip inside the zip


async def test_export_over_http_and_the_worker_is_org_scoped(
    real_client: httpx.AsyncClient,
    db_engine: AsyncEngine,
    task_app,
    users,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    monkeypatch,
):
    from tests.integration.test_matching_router import _add_profile

    ada, bob = users["ada"], users["bob"]
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)
    await _add_profile(real_client, fake_llm, ada)
    await _add_profile(real_client, fake_llm, bob)

    first = await real_client.post("/api/v1/me/export", headers=ada)
    again = await real_client.post("/api/v1/me/export", headers=ada)
    other = await real_client.post("/api/v1/me/export", headers=bob)
    assert first.status_code == 202 and first.json()["status_url"].endswith(
        first.json()["task_id"]
    )
    assert (
        again.json()["task_id"] == first.json()["task_id"]
    )  # still queued: no pile-up
    assert other.json()["task_id"] != first.json()["task_id"]
    assert (
        await real_client.get(first.json()["status_url"], headers=bob)
    ).status_code == 404

    await task_app.run_worker_async(wait=False, install_signal_handlers=False)

    results = {}
    for who, headers, resp in (("ada", ada, first), ("bob", bob, other)):
        done = (
            await real_client.get(resp.json()["status_url"], headers=headers)
        ).json()
        assert done["status"] == "done" and done["download_url"]
        zipped = zipfile.ZipFile(
            io.BytesIO((await real_client.get(done["download_url"])).content)
        )
        results[who] = _all_text(zipped)
    assert "ada-" in results["ada"] and "bob-" not in results["ada"]
    assert "bob-" in results["bob"] and "ada-" not in results["bob"]
