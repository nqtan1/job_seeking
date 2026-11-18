"""Career pack tools (ADR 0039) called as any agent or flow calls them: through the registry,
with a ``Call``. Each reads only its own account."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai.gateway import FakeLLMGateway
from recruitai.ai.prompts.letters import PROMPT_VERSION
from recruitai.core import tools
from recruitai.core.errors import NotFound
from recruitai.modules.agents.flows.models import Flow, FlowRun, FlowVersion
from recruitai.modules.applications.models import Application, ApplicationEvent
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


async def _situation(db, llm, org_id) -> dict | None:
    return await tools.read("situation", tools.Call(db, llm, org_id, None, None, {}))


async def test_situation_is_none_for_an_empty_account(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, _ = await _tenant(db_session, "sita", profile=False)
    assert await _situation(db_session, fake_llm, a.id) is None


async def test_situation_tells_stages_stale_cards_interviews_and_the_last_run(
    db_session: AsyncSession, fake_llm: FakeLLMGateway
):
    a, _ = await _tenant(db_session, "sitb", profile=False)
    b, _ = await _tenant(db_session, "sitc", profile=False)
    now = datetime.now(UTC)

    def card(org, company, title, status, moved, **kw):
        app = Application(
            org_id=org,
            company_name=company,
            job_title=title,
            source="other",
            status=status,
            **kw,
        )
        db_session.add(app)
        return app, moved

    cards = [
        card(a.id, "Acme", "ML Engineer", "applied", now - timedelta(days=9)),
        card(a.id, "Fresh", "Dev", "applied", now - timedelta(days=1)),
        card(a.id, "Saved1", None, "to_apply", now),
        card(
            a.id,
            "Beta",
            "Data Lead",
            "interview",
            now,
            interview_at=now + timedelta(days=2),
        ),
        card(b.id, "OtherCo", "Secret Role", "applied", now - timedelta(days=30)),
    ]
    await db_session.flush()
    for app, moved in cards:
        db_session.add(
            ApplicationEvent(
                application_id=app.id, org_id=app.org_id, to_status=app.status, at=moved
            )
        )
    for org, name in ((a.id, "Morning digest"), (b.id, "Other flow")):
        flow = Flow(org_id=org, name=name, current_version=1)
        db_session.add(flow)
        await db_session.flush()
        version = FlowVersion(
            org_id=org, flow_id=flow.id, version=1, graph={}, schema_version=1
        )
        db_session.add(version)
        await db_session.flush()
        db_session.add(
            FlowRun(
                org_id=org,
                flow_id=flow.id,
                flow_version_id=version.id,
                status="done",
                inputs={},
                finished_at=now - timedelta(days=2),
            )
        )
    await db_session.commit()

    text = (await _situation(db_session, fake_llm, a.id))["text"]
    assert len(text) <= 600
    assert "Tracker: 1 to apply, 2 applied, 1 interview" in text
    assert "No reply 9 days: ML Engineer @ Acme" in text and "Fresh" not in text
    assert f"Interview {(now + timedelta(days=2)).date()}: Data Lead @ Beta" in text
    assert "Last automation: Morning digest (done, 2 days ago)" in text
    assert "OtherCo" not in text and "Other flow" not in text  # another account's rows
