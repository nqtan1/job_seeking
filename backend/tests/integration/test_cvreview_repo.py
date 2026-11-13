import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.modules.cvreview import repository
from recruitai.modules.cvreview.schemas import LlmSummary, ReviewData, Strength
from tests.integration.test_letters_service import _tenant

DATA = ReviewData(
    blocks=[], comments=[], dimensions={}, pages=1,
    summary=LlmSummary(strengths=[Strength(text="s", block_id=None)], top_fixes=[]), grounding_rate=1.0,
)  # fmt: skip


async def _add(db: AsyncSession, org_id, score: int = 60):
    return await repository.add(
        db, org_id=org_id, document_id=None, parent_id=None,
        track="backend", level="mid", score=score, data=DATA, model="m", prompt_version="v@1",
    )  # fmt: skip


async def test_round_trip_and_cross_tenant(db_session: AsyncSession):
    a, _ = await _tenant(db_session, "cvra")
    b, _ = await _tenant(db_session, "cvrb")
    row = await _add(db_session, a.id)

    got = await repository.get(db_session, org_id=a.id, review_id=row.id)
    assert got and got.data["summary"]["strengths"][0]["text"] == "s" and got.created_at
    assert await repository.count_for_org(db_session, org_id=a.id) == 1

    assert await repository.get(db_session, org_id=b.id, review_id=row.id) is None
    assert (
        await repository.list_for_org(db_session, org_id=b.id, limit=10, offset=0) == []
    )
    assert not await repository.delete(db_session, org_id=b.id, review_id=row.id)
    assert await repository.delete(db_session, org_id=a.id, review_id=row.id)


async def test_score_check_rejects_101(db_session: AsyncSession):
    a, _ = await _tenant(db_session, "cvrc")
    with pytest.raises(IntegrityError):
        await _add(db_session, a.id, score=101)


async def test_queued_reviews_count_and_a_deleted_cv_takes_its_reviews(
    db_session: AsyncSession,
):
    from sqlalchemy import delete

    from recruitai.core.tasks import TaskRun
    from recruitai.modules.documents.models import Document

    a, _ = await _tenant(db_session, "cvrd")
    doc = Document(
        org_id=a.id,
        kind="cv",
        storage_key="k-cvrd",
        mime="text/plain",
        size=1,
        sha256="0" * 64,
    )
    db_session.add_all([doc, TaskRun(org_id=a.id, kind="cvreview.evaluate")])
    await db_session.flush()
    row = await repository.add(
        db_session, org_id=a.id, document_id=doc.id, parent_id=None,
        track="backend", level="mid", score=60, data=DATA, model="m", prompt_version="v@1",
    )  # fmt: skip
    assert (
        await repository.count_for_org(db_session, org_id=a.id) == 2
    )  # stored + queued

    await db_session.execute(delete(Document).where(Document.id == doc.id))
    assert await repository.get(db_session, org_id=a.id, review_id=row.id) is None
