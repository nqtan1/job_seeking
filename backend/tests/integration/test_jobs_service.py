"""jobs service against the real DB, with FakeLLMGateway, LocalStorage and a fake provider."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway, FilePart, TextPart
from recruitai.ai.prompts.jobs import PROMPT_VERSION
from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.storage import LocalStorage
from recruitai.modules.documents import service as documents
from recruitai.modules.identity.models import Organization, User
from recruitai.modules.jobs import service
from recruitai.modules.jobs.models import JobPosting
from tests.fixtures.jobs import FakeJobProvider
from tests.unit.test_jobs_parser import blank_job

PDF = b"%PDF-1.4\n%jd"


async def _org(db: AsyncSession, tag: str) -> Organization:
    org = Organization(name=tag, kind="personal")
    db.add_all([org, User(firebase_uid=f"fb-{tag}", email=f"{tag}@example.test")])
    await db.flush()
    return org


async def test_manual_job_is_extracted_post_processed_and_org_scoped(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, b = await _org(db_session, "a"), await _org(db_session, "b")
    fake_llm.queue(PROMPT_VERSION, blank_job())

    posting = await service.add_manual(
        db_session, fake_llm, org_id=a.id, text="CDI chez Acme à Paris"
    )
    assert (posting.source, posting.external_id, posting.title) == (
        "manual",
        None,
        "Dev Python",
    )
    assert posting.data["badges"]["contract_type"] == "CDI"  # filled by the parser
    assert any(
        isinstance(p, TextPart) and "CDI chez Acme" in p.text
        for p in fake_llm.calls[0].parts
    )

    assert [j.id for j in await service.list_jobs(db_session, org_id=a.id)] == [
        posting.id
    ]
    assert await service.list_jobs(db_session, org_id=b.id) == []
    with pytest.raises(NotFound):  # cross-tenant: another org's job id is a 404
        await service.get_job(db_session, org_id=b.id, job_id=posting.id)


async def test_file_job_checks_kind_and_ownership_before_any_llm_call(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    a, b = await _org(db_session, "a"), await _org(db_session, "b")
    jd, cv = [
        await documents.upload(
            db_session, fake_storage, org_id=a.id, uploaded_by=None, kind=kind, data=PDF
        )
        for kind in ("jd", "cv")
    ]

    with pytest.raises(NotFound):
        await service.add_from_file(
            db_session, fake_storage, fake_llm, org_id=b.id, document_id=jd.id
        )
    with pytest.raises(ValidationFailed):
        await service.add_from_file(
            db_session, fake_storage, fake_llm, org_id=a.id, document_id=cv.id
        )
    assert fake_llm.calls == []

    fake_llm.queue(PROMPT_VERSION, blank_job())
    posting = await service.add_from_file(
        db_session, fake_storage, fake_llm, org_id=a.id, document_id=jd.id
    )
    assert posting.source == "file"
    assert any(
        isinstance(p, FilePart) and p.data == PDF for p in fake_llm.calls[0].parts
    )


async def test_saving_a_search_result_is_idempotent_and_maps_without_llm(
    db_session: AsyncSession,
):
    org = await _org(db_session, "a")
    provider = FakeJobProvider()
    first = await service.save_search_result(
        db_session, provider, org_id=org.id, external_id="AB1"
    )
    again = await service.save_search_result(
        db_session, provider, org_id=org.id, external_id="AB1"
    )
    assert first.id == again.id
    assert await db_session.scalar(select(func.count()).select_from(JobPosting)) == 1
    assert first.source == "france_travail" and first.external_id == "AB1"
    assert first.data["profile"]["technical_skills"] == ["Python"]
    assert first.data["job_description_text"] == "Great job"
    with pytest.raises(NotFound):
        await service.save_search_result(
            db_session, provider, org_id=org.id, external_id="MISSING"
        )


async def test_search_is_cached_for_exactly_24_hours(db_session: AsyncSession):
    provider = FakeJobProvider()
    t0 = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    await service.search(db_session, provider, query="python", now=t0)
    await service.search(
        db_session, provider, query="python", now=t0 + timedelta(hours=23, minutes=59)
    )
    assert provider.searches == 1  # hit
    await service.search(db_session, provider, query="java", now=t0)
    assert provider.searches == 2  # different query = miss
    await service.search(
        db_session, provider, query="python", now=t0 + timedelta(hours=24)
    )
    assert provider.searches == 3  # the expiry instant itself is a miss
