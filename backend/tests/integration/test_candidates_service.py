"""candidates service against the real DB, with FakeLLMGateway and real LocalStorage (P2-03)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway, FilePart
from recruitai.ai.prompts.cv_extract import PROMPT_VERSION
from recruitai.core.errors import NotFound, UpstreamUnavailable, ValidationFailed
from recruitai.core.storage import LocalStorage
from recruitai.modules.candidates import service
from recruitai.modules.candidates.models import CandidateProfile
from recruitai.modules.candidates.schemas import (
    CVInformation,
    PersonalInfo,
    ProfileUpdate,
    RawSkill,
)
from recruitai.modules.documents import service as documents
from recruitai.modules.identity.models import Organization, User

PDF = b"%PDF-1.4\n%cv"


def _cv(name: str, skill: str = "Python") -> CVInformation:
    return CVInformation(
        personal_info=PersonalInfo(name=name, email="ada@example.com"),
        formations=[],
        experiences=[],
        skills=[RawSkill(name=skill)],
        summary="Engineer",
    )


async def _tenant(db: AsyncSession, storage: LocalStorage, tag: str, kind="cv"):
    org = Organization(name=tag, kind="personal")
    user = User(firebase_uid=f"fb-{tag}", email=f"{tag}@example.test")
    db.add_all([org, user])
    await db.flush()
    doc = await documents.upload(
        db, storage, org_id=org.id, uploaded_by=user.id, kind=kind, data=PDF
    )
    return org, doc


async def test_extract_upserts_and_update_merges_sections(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    org, doc = await _tenant(db_session, fake_storage, "ada")
    fake_llm.queue(PROMPT_VERSION, _cv("Ada Lovelace"))
    fake_llm.queue(PROMPT_VERSION, _cv("Ada L.", skill="Rust"))

    first = await service.extract(
        db_session, fake_storage, fake_llm, org_id=org.id, document_id=doc.id
    )
    assert (first.name, first.document_id, first.schema_version) == (
        "Ada Lovelace",
        doc.id,
        1,
    )
    # The CV travels as a file part and the call carries the versioned prompt id.
    call = fake_llm.calls[0]
    assert call.feature == PROMPT_VERSION
    assert any(isinstance(p, FilePart) and p.data == PDF for p in call.parts)

    second = await service.extract(
        db_session, fake_storage, fake_llm, org_id=org.id, document_id=doc.id
    )
    count = await db_session.scalar(select(func.count()).select_from(CandidateProfile))
    assert count == 1 and second.id == first.id
    assert second.data["skills"] == [{"name": "Rust", "category": None}]

    updated = await service.update_profile(
        db_session, org_id=org.id, changes=ProfileUpdate(summary="New summary")
    )
    assert updated.data["summary"] == "New summary"
    assert updated.data["skills"] == [{"name": "Rust", "category": None}]
    assert updated.document_id == doc.id


async def test_extract_rejects_non_cv_and_other_orgs_documents(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, fake_storage: LocalStorage
):
    org_a, _ = await _tenant(db_session, fake_storage, "a")
    _, doc_b = await _tenant(db_session, fake_storage, "b")
    _, jd_a = await _tenant(db_session, fake_storage, "c", kind="jd")

    with pytest.raises(NotFound):
        await service.extract(
            db_session, fake_storage, fake_llm, org_id=org_a.id, document_id=doc_b.id
        )
    with pytest.raises(ValidationFailed):
        await service.extract(
            db_session, fake_storage, fake_llm, org_id=jd_a.org_id, document_id=jd_a.id
        )
    assert fake_llm.calls == []  # rejected before any (billed) model call


async def test_get_and_update_without_a_profile_are_404(db_session: AsyncSession):
    org = Organization(name="x", kind="personal")
    db_session.add(org)
    await db_session.flush()
    with pytest.raises(NotFound):
        await service.get_profile(db_session, org_id=org.id)
    with pytest.raises(NotFound):
        await service.update_profile(
            db_session, org_id=org.id, changes=ProfileUpdate(summary="s")
        )


class _MalformedThenValid:
    """Fails with the gateways' "unparseable output" error ``failures`` times, then answers."""

    def __init__(self, failures: int, code: str = "ai_response_invalid") -> None:
        self.failures, self.code, self.calls = failures, code, 0

    async def generate(self, **_: object) -> CVInformation:
        self.calls += 1
        if self.calls <= self.failures:
            raise UpstreamUnavailable("bad output", code=self.code)
        return _cv("Ada Lovelace")


async def test_extract_retries_malformed_output_once_then_gives_a_clean_error(
    db_session: AsyncSession, fake_storage: LocalStorage
):
    org, doc = await _tenant(db_session, fake_storage, "retry")

    recovers = _MalformedThenValid(failures=1)
    profile = await service.extract(
        db_session,
        fake_storage,
        recovers,
        org_id=org.id,
        document_id=doc.id,  # type: ignore[arg-type]
    )
    assert recovers.calls == 2 and profile.name == "Ada Lovelace"

    always_bad = _MalformedThenValid(failures=5)
    with pytest.raises(UpstreamUnavailable) as err:
        await service.extract(
            db_session,
            fake_storage,
            always_bad,
            org_id=org.id,
            document_id=doc.id,  # type: ignore[arg-type]
        )
    assert always_bad.calls == 2 and err.value.code == "ai_response_invalid"

    timing_out = _MalformedThenValid(failures=5, code="ai_timeout")
    with pytest.raises(UpstreamUnavailable):
        await service.extract(
            db_session,
            fake_storage,
            timing_out,
            org_id=org.id,
            document_id=doc.id,  # type: ignore[arg-type]
        )
    assert timing_out.calls == 1  # only malformed output is retried, not a timeout
