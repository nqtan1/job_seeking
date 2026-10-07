"""letters service against the real DB with FakeLLMGateway (P2-17)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway, TextPart
from recruitai.ai.prompts.letters import PROMPT_VERSION
from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.modules.candidates import repository as candidates_repo
from recruitai.modules.candidates.schemas import CVInformation, PersonalInfo, RawSkill
from recruitai.modules.identity.models import Organization, User
from recruitai.modules.jobs import repository as jobs_repo
from recruitai.modules.letters import service
from recruitai.modules.letters.schemas import BlockText, LetterDraft
from tests.unit.test_jobs_parser import blank_job

DRAFT = LetterDraft(
    subject="Candidature Développeur Python",
    salutation="Madame, Monsieur,",
    opening="Je vous écris pour ...",
    body=["Chez Brightwave, j'ai ...", "Je souhaite ...", "Mon profil ..."],
    closing="Veuillez agréer mes salutations distinguées.",
)
NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


async def _tenant(db: AsyncSession, tag: str, *, profile: bool = True):
    org = Organization(name=tag, kind="personal")
    db.add_all([org, User(firebase_uid=f"fb-{tag}", email=f"{tag}@example.test")])
    await db.flush()
    if profile:
        await candidates_repo.upsert(
            db,
            org_id=org.id,
            document_id=None,
            info=CVInformation(
                personal_info=PersonalInfo(
                    name="Lucas Martel", email="lucas@example.test", phone="0102030405"
                ),
                formations=[],
                experiences=[],
                skills=[RawSkill(name="Python")],
            ),
        )
    job = await jobs_repo.add(
        db, org_id=org.id, source="manual", external_id=None, info=blank_job()
    )
    return org, job


async def test_generate_fills_programmatic_blocks_and_needs_no_fit_analysis(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    org, job = await _tenant(db_session, "a")
    fake_llm.queue(PROMPT_VERSION, DRAFT)

    letter = await service.generate(
        db_session,
        fake_llm,
        org_id=org.id,
        job_id=job.id,
        language="fr",
        tone="warm",
        company_type="startup",
        now=NOW,
    )

    c = letter.content
    assert c["subject"] == DRAFT.subject and c["body"] == DRAFT.body
    assert c["header"] == {
        "name": "Lucas Martel", "email": "lucas@example.test",
        "phone": "0102030405", "address": None, "date": "2026-10-02",
    }  # fmt: skip
    assert c["recipient"]["company"] == "Acme" and c["signature"] == "Lucas Martel"
    assert (letter.status, letter.render_status, letter.template) == (
        "draft",
        "none",
        "classic",
    )
    call = fake_llm.calls[0]
    assert call.model == "smart" and "startup culture" in call.system
    sent = " ".join(p.text for p in call.parts if isinstance(p, TextPart))
    assert "<candidate_profile>" in sent and "Lucas Martel" in sent
    versions = await service.list_versions(
        db_session, org_id=org.id, letter_id=letter.id
    )
    assert [v.n for v in versions] == [1]


async def test_regenerating_or_editing_one_block_leaves_the_rest_and_keeps_history(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    org, job = await _tenant(db_session, "a")
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    letter = await service.generate(
        db_session, fake_llm, org_id=org.id, job_id=job.id, now=NOW
    )
    original = dict(letter.content)

    fake_llm.queue(PROMPT_VERSION, BlockText(text="  Nouveau paragraphe.  "))
    regenerated = await service.regenerate_block(
        db_session, fake_llm, org_id=org.id, letter_id=letter.id, block="body", index=1
    )
    assert regenerated.content["body"] == [
        DRAFT.body[0],
        "Nouveau paragraphe.",
        DRAFT.body[2],
    ]
    assert {k: v for k, v in regenerated.content.items() if k != "body"} == {
        k: v for k, v in original.items() if k != "body"
    }
    assert "body (paragraph 1)" in fake_llm.calls[-1].system

    edited = await service.edit_block(
        db_session,
        org_id=org.id,
        letter_id=letter.id,
        block="subject",
        text="Mon objet",
    )
    assert edited.content["subject"] == "Mon objet"
    assert edited.content["body"][1] == "Nouveau paragraphe."

    versions = await service.list_versions(
        db_session, org_id=org.id, letter_id=letter.id
    )
    assert [v.n for v in versions] == [3, 2, 1]  # newest first, one per change
    assert versions[-1].content == original

    restored = await service.restore_version(
        db_session, org_id=org.id, letter_id=letter.id, n=1
    )
    assert restored.content == original
    after = await service.list_versions(db_session, org_id=org.id, letter_id=letter.id)
    assert [v.n for v in after] == [4, 3, 2, 1]  # history is append-only
    with pytest.raises(NotFound):
        await service.restore_version(
            db_session, org_id=org.id, letter_id=letter.id, n=99
        )


async def test_invalid_blocks_and_missing_inputs_cost_no_model_call(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    org, job = await _tenant(db_session, "a")
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    letter = await service.generate(
        db_session, fake_llm, org_id=org.id, job_id=job.id, now=NOW
    )
    calls = len(fake_llm.calls)

    for kwargs in (
        {"block": "body"},
        {"block": "body", "index": 9},
        {"block": "subject", "index": 0},
    ):
        with pytest.raises(ValidationFailed):
            await service.regenerate_block(
                db_session, fake_llm, org_id=org.id, letter_id=letter.id, **kwargs
            )
    for text in ("", "   ", "x" * 5001):
        with pytest.raises(ValidationFailed):
            await service.edit_block(
                db_session,
                org_id=org.id,
                letter_id=letter.id,
                block="opening",
                text=text,
            )

    bare, bare_job = await _tenant(db_session, "bare", profile=False)
    with pytest.raises(ValidationFailed):  # no profile yet
        await service.generate(db_session, fake_llm, org_id=bare.id, job_id=bare_job.id)
    assert len(fake_llm.calls) == calls


async def test_other_orgs_cannot_see_edit_regenerate_or_restore_a_letter(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, job_a = await _tenant(db_session, "a")
    b, _ = await _tenant(db_session, "b")
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    letter = await service.generate(
        db_session, fake_llm, org_id=a.id, job_id=job_a.id, now=NOW
    )
    calls = len(fake_llm.calls)

    with pytest.raises(NotFound):
        await service.get_letter(db_session, org_id=b.id, letter_id=letter.id)
    with pytest.raises(NotFound):
        await service.edit_block(
            db_session, org_id=b.id, letter_id=letter.id, block="subject", text="hacked"
        )
    with pytest.raises(NotFound):
        await service.regenerate_block(
            db_session, fake_llm, org_id=b.id, letter_id=letter.id, block="subject"
        )
    with pytest.raises(NotFound):
        await service.list_versions(db_session, org_id=b.id, letter_id=letter.id)
    with pytest.raises(NotFound):
        await service.restore_version(db_session, org_id=b.id, letter_id=letter.id, n=1)
    with pytest.raises(NotFound):  # B cannot write a letter against A's job either
        await service.generate(db_session, fake_llm, org_id=b.id, job_id=job_a.id)
    assert await service.list_letters(db_session, org_id=b.id) == []
    assert len(fake_llm.calls) == calls


@pytest.mark.parametrize(
    ("action", "needle"),
    [
        ("shorten", "Shorten"),
        ("more_formal", "formal"),
        ("more_concrete", "concrete"),
        ("add_metric", "do NOT invent"),
        ("fix_grammar", "spelling, grammar"),
    ],
)
async def test_assist_returns_a_suggestion_per_action_and_never_changes_the_letter(
    db_session: AsyncSession, fake_llm: FakeLLMGateway, action: str, needle: str
):
    org, job = await _tenant(db_session, "a")
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    letter = await service.generate(
        db_session, fake_llm, org_id=org.id, job_id=job.id, now=NOW
    )
    before = dict(letter.content)
    fake_llm.queue("letter_assist@1", BlockText(text="  Version réécrite.  "))

    suggestion = await service.assist(
        db_session,
        fake_llm,
        org_id=org.id,
        letter_id=letter.id,
        block="body",
        selection="Je souhaite ...",
        action=action,  # type: ignore[arg-type]
    )

    assert suggestion == "Version réécrite."
    call = fake_llm.calls[-1]
    assert needle in call.system and call.model == "fast"
    assert "Je souhaite ..." in " ".join(
        p.text for p in call.parts if isinstance(p, TextPart)
    )
    after = await service.get_letter(db_session, org_id=org.id, letter_id=letter.id)
    assert after.content == before  # nothing saved
    versions = await service.list_versions(
        db_session, org_id=org.id, letter_id=letter.id
    )
    assert [v.n for v in versions] == [1]


async def test_assist_rejects_a_selection_outside_the_block_and_other_orgs(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, job = await _tenant(db_session, "a")
    b, _ = await _tenant(db_session, "b")
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    letter = await service.generate(
        db_session, fake_llm, org_id=a.id, job_id=job.id, now=NOW
    )
    calls = len(fake_llm.calls)

    for block, selection in (
        ("subject", "Je souhaite ..."),
        ("body", "not in the letter"),
        ("body", "  "),
    ):
        with pytest.raises(ValidationFailed):
            await service.assist(
                db_session, fake_llm, org_id=a.id, letter_id=letter.id,
                block=block, selection=selection, action="shorten",
            )  # fmt: skip
    with pytest.raises(NotFound):
        await service.assist(
            db_session, fake_llm, org_id=b.id, letter_id=letter.id,
            block="body", selection="Je souhaite ...", action="shorten",
        )  # fmt: skip
    assert len(fake_llm.calls) == calls  # none of these reached the model


async def test_check_and_export_cope_with_a_deleted_job_and_refuse_without_a_profile(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    from sqlalchemy import delete

    from recruitai.modules.candidates.models import CandidateProfile
    from recruitai.modules.jobs.models import JobPosting

    org, job = await _tenant(db_session, "a")
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    letter = await service.generate(
        db_session, fake_llm, org_id=org.id, job_id=job.id, now=NOW
    )

    await db_session.execute(
        delete(JobPosting).where(JobPosting.id == job.id)
    )  # job_id -> NULL
    await db_session.refresh(letter)
    assert letter.job_id is None
    checked = await service.check_letter(db_session, org_id=org.id, letter_id=letter.id)
    assert checked.quality.keyword_coverage.ratio is None  # no job: nothing to cover
    subject, body = await service.export_letter(
        db_session, org_id=org.id, letter_id=letter.id, fmt="email"
    )
    assert subject == DRAFT.subject and DRAFT.closing in body
    assert (
        await service.export_letter(
            db_session, org_id=org.id, letter_id=letter.id, fmt="text"
        )
    )[0] is None

    await db_session.execute(
        delete(CandidateProfile).where(CandidateProfile.org_id == org.id)
    )
    with pytest.raises(ValidationFailed):
        await service.check_letter(db_session, org_id=org.id, letter_id=letter.id)
