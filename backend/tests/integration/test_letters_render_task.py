"""letters:render_pdf against the real DB, storage and worker, with a fake compiler (P2-20).
The real Tectonic binary is exercised separately, inside the worker image (CI)."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.letters import PROMPT_VERSION
from recruitai.core.auth import CurrentUser
from recruitai.core.storage import LocalStorage
from recruitai.core.tasks import TaskRun, enqueue
from recruitai.core.tenancy import OrgContext, get_org_context
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.candidates.schemas import CVInformation, PersonalInfo, RawSkill
from recruitai.modules.documents.models import Document
from recruitai.modules.jobs import repository as jobs_repo
from recruitai.modules.letters import service, tasks
from recruitai.modules.letters.models import Letter
from recruitai.worker import render_pdf
from tests.fixtures.db import purge_tenant
from tests.integration.test_letters_service import DRAFT
from tests.unit.test_jobs_parser import blank_job

PDF = b"%PDF-1.4 fake letter"


@pytest.fixture
async def committed_letter(
    db_engine: AsyncEngine,
) -> AsyncIterator[tuple[OrgContext, UUID]]:
    """A real, committed letter (the worker uses its own connection); cleaned up after."""
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        ctx = await get_org_context(
            CurrentUser(firebase_uid=f"uid-{uuid4().hex[:8]}", email="r@example.test"),
            session,
            x_org_id=None,
        )
        await candidates_repo.upsert(
            session,
            org_id=ctx.org_id,
            document_id=None,
            info=CVInformation(
                personal_info=PersonalInfo(name="Ada"),
                formations=[],
                experiences=[],
                skills=[RawSkill(name="Python")],
            ),
        )
        job = await jobs_repo.add(
            session,
            org_id=ctx.org_id,
            source="manual",
            external_id=None,
            info=blank_job(),
        )
        llm = FakeLLMGateway()
        llm.queue(PROMPT_VERSION, DRAFT)
        letter = await service.generate(session, llm, org_id=ctx.org_id, job_id=job.id)
    yield ctx, letter.id
    await purge_tenant(db_engine, org_id=ctx.org_id, user_id=ctx.user_id)


async def _letter(db_engine: AsyncEngine, letter_id: UUID) -> Letter:
    async with AsyncSession(db_engine) as session:
        return (
            await session.execute(select(Letter).where(Letter.id == letter_id))
        ).scalar_one()


async def _run(
    db_engine: AsyncEngine, task_app, ctx: OrgContext, letter_id: UUID
) -> UUID:
    async with AsyncSession(db_engine) as session:
        letter = (
            await session.execute(select(Letter).where(Letter.id == letter_id))
        ).scalar_one()
        letter.render_status = (
            "queued"  # what POST /render does, in the same transaction
        )
        run_id = await enqueue(
            session,
            task=render_pdf,
            org_id=ctx.org_id,
            kind="letters.render_pdf",
            task_kwargs={"org_id": str(ctx.org_id), "letter_id": str(letter_id)},
        )
        await session.commit()
    await task_app.run_worker_async(wait=False, install_signal_handlers=False)
    return run_id


async def _task_run(db_engine: AsyncEngine, run_id: UUID) -> TaskRun:
    async with AsyncSession(db_engine) as session:
        return (
            await session.execute(select(TaskRun).where(TaskRun.id == run_id))
        ).scalar_one()


async def test_worker_renders_stores_and_links_the_pdf(
    db_engine: AsyncEngine,
    task_app,
    committed_letter,
    fake_storage: LocalStorage,
    monkeypatch,
):
    ctx, letter_id = committed_letter
    seen: list[str] = []

    async def fake_compile(tex: str) -> bytes:
        seen.append(tex)
        return PDF

    monkeypatch.setattr(tasks, "compile_tex", fake_compile)
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)

    run_id = await _run(db_engine, task_app, ctx, letter_id)

    run = await _task_run(db_engine, run_id)
    letter = await _letter(db_engine, letter_id)
    assert (run.status, run.error_code) == ("done", None)
    assert (
        letter.render_status == "done" and str(letter.pdf_document_id) == run.result_ref
    )
    assert (
        DRAFT.subject in seen[0] and r"\documentclass" in seen[0]
    )  # the template output
    async with AsyncSession(db_engine) as session:
        doc = (
            await session.execute(
                select(Document).where(Document.id == letter.pdf_document_id)
            )
        ).scalar_one()
    assert (doc.kind, doc.org_id, doc.mime) == (
        "letter_pdf",
        ctx.org_id,
        "application/pdf",
    )
    assert await fake_storage.get(doc.storage_key) == PDF


async def test_raw_latex_override_skips_the_template_and_forbidden_input_fails_at_once(
    db_engine: AsyncEngine,
    task_app,
    committed_letter,
    fake_storage: LocalStorage,
    monkeypatch,
):
    ctx, letter_id = committed_letter
    compiled: list[str] = []

    async def fake_compile(tex: str) -> bytes:
        compiled.append(tex)
        return PDF

    monkeypatch.setattr(tasks, "compile_tex", fake_compile)
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)

    async def set_override(text: str) -> None:
        async with AsyncSession(db_engine) as session:
            letter = (
                await session.execute(select(Letter).where(Letter.id == letter_id))
            ).scalar_one()
            letter.latex_override = text
            await session.commit()

    await set_override("\\documentclass{article}\\begin{document}mine\\end{document}")
    assert (
        await _task_run(db_engine, await _run(db_engine, task_app, ctx, letter_id))
    ).status == "done"
    assert compiled == ["\\documentclass{article}\\begin{document}mine\\end{document}"]

    compiled.clear()
    await set_override(
        "\\documentclass{article}\\begin{document}\\write18{x}\\end{document}"
    )
    run = await _task_run(db_engine, await _run(db_engine, task_app, ctx, letter_id))
    letter = await _letter(db_engine, letter_id)
    assert (run.status, run.error_code) == ("failed", "render_forbidden_input")
    assert (
        letter.render_status == "failed" and compiled == []
    )  # never reached the compiler


async def test_transient_failures_retry_then_fail_with_a_safe_code(
    db_engine: AsyncEngine, committed_letter, fake_storage: LocalStorage, monkeypatch
):
    ctx, letter_id = committed_letter

    async def broken_compile(tex: str) -> bytes:
        raise tasks.RenderError("render_timeout", retryable=True)

    monkeypatch.setattr(tasks, "compile_tex", broken_compile)
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)
    async with AsyncSession(db_engine) as session:
        run_id = uuid4()
        session.add(TaskRun(id=run_id, org_id=ctx.org_id, kind="letters.render_pdf"))
        letter = (
            await session.execute(select(Letter).where(Letter.id == letter_id))
        ).scalar_one()
        letter.render_status = "queued"
        await session.commit()
    kwargs = {
        "task_run_id": str(run_id),
        "org_id": str(ctx.org_id),
        "letter_id": str(letter_id),
    }

    for attempts in (0, 1):  # not the last attempt: raise so Procrastinate retries
        with pytest.raises(RuntimeError, match="render_timeout"):
            await render_pdf.func(
                SimpleNamespace(job=SimpleNamespace(attempts=attempts)), **kwargs
            )
        assert (await _task_run(db_engine, run_id)).status == "queued"

    await render_pdf.func(
        SimpleNamespace(job=SimpleNamespace(attempts=2)), **kwargs
    )  # 3rd
    run = await _task_run(db_engine, run_id)
    assert (run.status, run.error_code) == ("failed", "render_timeout")
    assert (await _letter(db_engine, letter_id)).render_status == "failed"


async def test_editing_resets_the_render_and_a_new_render_replaces_the_old_pdf(
    db_engine: AsyncEngine,
    task_app,
    committed_letter,
    fake_storage: LocalStorage,
    monkeypatch,
):
    ctx, letter_id = committed_letter

    async def fake_compile(tex: str) -> bytes:
        return PDF

    monkeypatch.setattr(tasks, "compile_tex", fake_compile)
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)

    await _run(db_engine, task_app, ctx, letter_id)
    first = await _letter(db_engine, letter_id)
    assert first.render_status == "done"

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        await service.edit_block(
            session,
            org_id=ctx.org_id,
            letter_id=letter_id,
            block="subject",
            text="New subject",
        )
    edited = await _letter(db_engine, letter_id)
    assert edited.render_status == "none"  # the PDF no longer matches the text

    await _run(db_engine, task_app, ctx, letter_id)
    second = await _letter(db_engine, letter_id)
    assert (
        second.render_status == "done"
        and second.pdf_document_id != first.pdf_document_id
    )
    async with AsyncSession(db_engine) as session:
        pdfs = (
            (
                await session.execute(
                    select(Document).where(
                        Document.org_id == ctx.org_id, Document.kind == "letter_pdf"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [d.id for d in pdfs] == [
        second.pdf_document_id
    ]  # the first PDF is gone, not orphaned


async def test_a_letter_edited_while_compiling_gets_no_stale_pdf(
    db_engine: AsyncEngine,
    task_app,
    committed_letter,
    fake_storage: LocalStorage,
    monkeypatch,
):
    ctx, letter_id = committed_letter

    async def compile_while_the_user_edits(tex: str) -> bytes:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await service.edit_block(
                session,
                org_id=ctx.org_id,
                letter_id=letter_id,
                block="subject",
                text="Edited now",
            )
        return PDF

    monkeypatch.setattr(tasks, "compile_tex", compile_while_the_user_edits)
    monkeypatch.setattr("recruitai.worker.storage", fake_storage)

    run_id = await _run(db_engine, task_app, ctx, letter_id)

    run = await _task_run(db_engine, run_id)
    letter = await _letter(db_engine, letter_id)
    assert (run.status, run.error_code) == ("failed", "letter_changed")
    assert letter.render_status == "none" and letter.pdf_document_id is None
    async with AsyncSession(db_engine) as session:
        left = (
            (
                await session.execute(
                    select(Document).where(
                        Document.org_id == ctx.org_id, Document.kind == "letter_pdf"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert left == []  # the discarded PDF left no row behind
