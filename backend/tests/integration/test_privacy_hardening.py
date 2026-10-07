"""Export/delete edge cases end to end (P2-32): a failed export never leaves a link to an
incomplete ZIP, and deleting and exporting in either order never leaves or resurrects data."""

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.core.storage import LocalStorage, ObjectNotFound
from recruitai.modules.coach import service as coach_service
from recruitai.modules.documents.models import Document
from recruitai.modules.privacy import service
from recruitai.modules.privacy.tasks import export_user_data
from tests.fixtures.org_data import seed_org


async def _exports(db: AsyncSession, org_id) -> list[Document]:
    rows = await db.execute(
        select(Document).where(Document.org_id == org_id, Document.kind == "export")
    )
    return list(rows.scalars())


async def _no_identity() -> None:
    return None


async def test_a_failure_while_gathering_or_storing_keeps_the_previous_export_and_adds_none(
    db_session: AsyncSession,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    monkeypatch,
):
    a = await seed_org(db_session, "alpha", llm=fake_llm, storage=fake_storage)
    first_id = await service.build_export(
        db_session, fake_storage, org_id=a.org_id, user_id=a.user_id
    )
    await db_session.commit()
    first = (await _exports(db_session, a.org_id))[0]
    assert first.id == first_id

    async def boom(*_: object, **__: object):
        raise RuntimeError("module blew up halfway")

    with monkeypatch.context() as m:  # failing while gathering one module's data
        m.setattr(coach_service, "export_data", boom)
        with pytest.raises(RuntimeError):
            await service.build_export(
                db_session, fake_storage, org_id=a.org_id, user_id=a.user_id
            )
    await db_session.rollback()

    real_put = fake_storage.put

    async def failing_put(key: str, data: bytes, **kw: object) -> None:
        if "/export/" in key:
            raise OSError("disk full")
        await real_put(key, data, **kw)  # type: ignore[arg-type]

    with monkeypatch.context() as m:  # failing while storing the new ZIP
        m.setattr(fake_storage, "put", failing_put)
        with pytest.raises(OSError):
            await service.build_export(
                db_session, fake_storage, org_id=a.org_id, user_id=a.user_id
            )
    await db_session.rollback()

    assert [d.id for d in await _exports(db_session, a.org_id)] == [
        first.id
    ]  # exactly the old one
    assert (await fake_storage.get(first.storage_key)).startswith(
        b"PK"
    )  # and it still downloads


async def test_the_worker_task_fails_cleanly_and_polling_offers_no_download(
    real_client: httpx.AsyncClient,
    db_engine,
    task_app,
    users,
    fake_llm: FakeLLMGateway,
    fake_storage: LocalStorage,
    monkeypatch,
):
    from tests.integration.test_matching_router import _add_profile

    ada = users["ada"]
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)
    await _add_profile(real_client, fake_llm, ada)
    accepted = (await real_client.post("/api/v1/me/export", headers=ada)).json()
    me = (await real_client.get("/api/v1/me", headers=ada)).json()

    async def boom(*_: object, **__: object):
        raise RuntimeError("module blew up halfway")

    monkeypatch.setattr(coach_service, "export_data", boom)
    kwargs = {
        "task_run_id": accepted["task_id"],
        "org_id": me["active_org_id"],
        "user_id": me["user"]["id"],
    }
    for attempts in (0, 1):  # not the last attempt: raised so Procrastinate retries
        with pytest.raises(RuntimeError, match="export_failed"):
            await export_user_data.func(
                SimpleNamespace(job=SimpleNamespace(attempts=attempts)), **kwargs
            )
    await export_user_data.func(
        SimpleNamespace(job=SimpleNamespace(attempts=2)), **kwargs
    )  # last

    status = (await real_client.get(accepted["status_url"], headers=ada)).json()
    assert status["status"] == "failed" and status["error_code"] == "export_failed"
    assert status["download_url"] is None and status["result_ref"] is None
    assert "RuntimeError" not in str(status) and "blew up" not in str(
        status
    )  # nothing leaks
    async with AsyncSession(db_engine) as session:
        assert (
            await _exports(session, me["active_org_id"]) == []
        )  # no half-built archive anywhere


async def test_export_then_delete_removes_the_archive_too(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    a = await seed_org(db_session, "alpha", llm=fake_llm, storage=fake_storage)
    await service.build_export(
        db_session, fake_storage, org_id=a.org_id, user_id=a.user_id
    )
    await db_session.commit()
    archive = (await _exports(db_session, a.org_id))[0]
    assert await fake_storage.get(archive.storage_key)

    await service.delete_account(
        db_session, fake_storage, user_id=a.user_id, delete_identity=_no_identity
    )

    with pytest.raises(ObjectNotFound):
        await fake_storage.get(
            archive.storage_key
        )  # the personal-data ZIP did not outlive the account
    assert await _exports(db_session, a.org_id) == []


async def test_delete_then_export_fails_and_resurrects_nothing(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    a = await seed_org(db_session, "alpha", llm=fake_llm, storage=fake_storage)
    await service.delete_account(
        db_session, fake_storage, user_id=a.user_id, delete_identity=_no_identity
    )

    # a job that was already running when the account was deleted
    with pytest.raises(NoResultFound):
        await service.build_export(
            db_session, fake_storage, org_id=a.org_id, user_id=a.user_id
        )
    await db_session.rollback()

    assert await _exports(db_session, a.org_id) == []
    for key in a.document_keys:
        with pytest.raises(ObjectNotFound):
            await fake_storage.get(key)
    assert not (
        fake_storage.root / "orgs" / str(a.org_id)
    ).exists()  # no object under the org prefix
