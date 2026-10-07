"""The four scheduled sweep tasks themselves (the worker's entry points), run against the real
database, storage and Firebase emulator: the service logic is tested on a fake clock elsewhere;
this proves the wiring (session, storage, email, Firebase deletion) really works."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import firebase_admin
import pytest
from firebase_admin import auth as firebase_auth
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.usage import AiCall
from recruitai.core.storage import LocalStorage
from recruitai.modules.documents import service as documents
from recruitai.modules.documents.models import Document
from recruitai.modules.identity.models import Membership, Organization, User
from recruitai.modules.jobs.models import JobSearchCache
from recruitai.modules.privacy import tasks
from tests.fixtures.auth import mint_emulator_token


def _run(
    task,
):  # a Procrastinate task's coroutine, called the way a periodic tick would
    return task.func(timestamp=0)


async def test_the_scheduled_sweeps_do_their_work_through_the_workers_resources(
    db_engine: AsyncEngine, fake_storage: LocalStorage, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)
    tag = uuid4().hex[:8]
    uid, email = f"uid-sweep-{tag}", f"sweep-{tag}@example.com"
    mint_emulator_token(
        uid, email
    )  # a real Firebase identity for the account to be deleted
    now = datetime.now(UTC)
    org = Organization(name=tag, kind="personal")
    user = User(firebase_uid=uid, email=email, last_active_at=now - timedelta(days=800))

    try:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            session.add_all([org, user])
            await session.flush()
            session.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
            session.add(
                JobSearchCache(
                    key=f"k-{tag}",
                    provider="p",
                    payload={},
                    expires_at=now - timedelta(hours=1),
                )
            )
            session.add(
                AiCall(org_id=org.id, user_id=user.id, feature="f", model="m", prompt_version="f@1",
                       latency_ms=1, status="ok", created_at=now - timedelta(days=400))
            )  # fmt: skip
            export = await documents.store_generated(
                session,
                fake_storage,
                org_id=org.id,
                kind="export",
                data=b"PK",
                mime="application/zip",
            )
            await session.execute(
                update(Document)
                .where(Document.id == export.id)
                .values(created_at=now - timedelta(hours=30))
            )
            await session.commit()
            export_key = export.storage_key

        await _run(tasks.sweep_job_search_cache)
        await _run(tasks.sweep_exports)
        await _run(tasks.sweep_ai_calls)

        async with AsyncSession(db_engine) as session:
            assert (
                await session.execute(
                    select(JobSearchCache).where(JobSearchCache.key == f"k-{tag}")
                )
            ).first() is None
            assert (
                await session.execute(select(Document).where(Document.id == export.id))
            ).first() is None
            assert (
                await session.execute(select(AiCall).where(AiCall.org_id == org.id))
            ).first() is None
        assert not (
            fake_storage.root / export_key
        ).exists()  # the object went with the row

        # Inactive for 800 days and never warned: the first run only warns (EMAIL_BACKEND=fake).
        await _run(tasks.sweep_inactive_accounts)
        async with AsyncSession(db_engine) as session:
            warned = await session.scalar(
                select(User.deletion_warned_at).where(User.id == user.id)
            )
        assert warned is not None  # warned, not deleted
        assert firebase_auth.get_user(uid, app=firebase_admin.get_app()).email == email

        # A week later the warning is old enough: the account, its org and its identity go.
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE users SET deletion_warned_at = :t WHERE id = :u"),
                {"t": now - timedelta(days=8), "u": user.id},
            )
        await _run(tasks.sweep_inactive_accounts)
        async with AsyncSession(db_engine) as session:
            assert (
                await session.execute(select(User).where(User.id == user.id))
            ).first() is None
            assert (
                await session.execute(
                    select(Organization).where(Organization.id == org.id)
                )
            ).first() is None
        with pytest.raises(firebase_auth.UserNotFoundError):
            firebase_auth.get_user(uid, app=firebase_admin.get_app())
    finally:
        async with db_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM organizations WHERE id = :o"), {"o": org.id}
            )
            await conn.execute(
                text("DELETE FROM users WHERE firebase_uid = :u"), {"u": uid}
            )
            await conn.execute(
                text("DELETE FROM job_search_cache WHERE key = :k"), {"k": f"k-{tag}"}
            )
        try:
            firebase_auth.delete_user(uid, app=firebase_admin.get_app())
        except (firebase_auth.UserNotFoundError, ValueError):
            pass
