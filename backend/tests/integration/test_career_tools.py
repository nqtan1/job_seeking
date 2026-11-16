"""Career pack tools (ADR 0039) called as any agent or flow calls them: through the registry,
with a ``Call``. Each reads only its own account."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.letters import PROMPT_VERSION
from recruitai.core import tools
from recruitai.core.errors import NotFound
from recruitai.modules.cvreview import repository as cv_repo
from recruitai.modules.cvreview.schemas import (
    BlockComment,
    LlmSummary,
    ReviewData,
    Strength,
)
from recruitai.modules.identity.models import User
from recruitai.modules.letters.models import Letter
from tests.fixtures.fit import FIT, FIT_VERSION
from tests.integration.test_letters_service import DRAFT, _tenant


async def run(db, llm, tool: str, org_id, job_id=None, user_id=None) -> dict:
    call = tools.Call(db, llm, org_id, user_id, job_id, {})
    return await tools.handler(tool)(call)


async def test_profile_read_gives_the_summary_and_skills_and_no_contact_details(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, _ = await _tenant(db_session, "pra")
    b, _ = await _tenant(db_session, "prb", profile=False)
    out = await run(db_session, fake_llm, "profile_read", a.id)
    assert out == {"summary": "", "skills": "Python"}  # the name, email, phone stay out
    with pytest.raises(NotFound):  # another account's profile is never read
        await run(db_session, fake_llm, "profile_read", b.id)
    assert tools.get("profile_read").page == "/profile"


async def test_cv_review_latest_gives_the_newest_score_and_its_fixes(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, _ = await _tenant(db_session, "cvta")
    b, _ = await _tenant(db_session, "cvtb")

    async def add(score: int, fix: str) -> None:
        comment = BlockComment(
            block_id="b2", criterion="impact.metric", citations=[], why="No number.",
            improve=fix, rewrite=None, rating="poor",
        )  # fmt: skip
        data = ReviewData(
            blocks=[], comments=[comment], dimensions={}, pages=1, grounding_rate=1.0,
            summary=LlmSummary(strengths=[Strength(text="s", block_id=None)], top_fixes=["b2"]),
        )  # fmt: skip
        await cv_repo.add(
            db_session, org_id=a.id, document_id=None, parent_id=None, track="backend",
            level="mid", score=score, data=data, model="m", prompt_version="v@1",
        )  # fmt: skip
        await db_session.commit()

    with pytest.raises(NotFound):  # none yet: it never starts one
        await run(db_session, fake_llm, "cv_review_latest", a.id)
    await add(50, "Old advice.")
    await add(72, "Add a metric.")
    out = await run(db_session, fake_llm, "cv_review_latest", a.id)
    assert out == {"score": "72", "top_fixes": "- Add a metric."}
    with pytest.raises(NotFound):  # another account sees none of them
        await run(db_session, fake_llm, "cv_review_latest", b.id)
    assert fake_llm.calls == []


async def test_letter_draft_writes_a_letter_for_the_job_of_this_account_only(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, job = await _tenant(db_session, "lta")
    b, _ = await _tenant(db_session, "ltb")
    user = (
        await db_session.execute(select(User).where(User.firebase_uid == "fb-lta"))
    ).scalar_one()
    fake_llm.queue(FIT_VERSION, FIT)
    fake_llm.queue(PROMPT_VERSION, DRAFT)
    out = await run(
        db_session, fake_llm, "letter_draft", a.id, job_id=job.id, user_id=user.id
    )
    letter = await db_session.get(Letter, UUID(out["letter_id"]))
    assert letter is not None and letter.org_id == a.id and letter.job_id == job.id
    assert out["subject"] == DRAFT.subject and len(fake_llm.calls) == 2

    with pytest.raises(
        NotFound
    ):  # another account's job: refused before any model call
        await run(
            db_session, fake_llm, "letter_draft", b.id, job_id=job.id, user_id=user.id
        )
    assert len(fake_llm.calls) == 2
    with pytest.raises(tools.NoJob):
        await run(db_session, fake_llm, "letter_draft", a.id, user_id=user.id)
