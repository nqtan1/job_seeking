"""radar tables (A-02): bounds, the "seen" ledger, tenant filtering and cascades."""

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.auth import CurrentUser
from recruitai.core.tenancy import get_org_context
from recruitai.modules.radar import repository as repo
from recruitai.modules.radar.models import RadarResult


async def _org(db: AsyncSession, tag: str):
    ctx = await get_org_context(
        CurrentUser(
            f"uid-radar-{tag}-{uuid4().hex[:6]}",
            f"{tag}-{uuid4().hex[:6]}@example.test",
        ),
        db,
        x_org_id=None,
    )
    return ctx.org_id


async def _search(db: AsyncSession, org_id, **over):
    values = {"name": "Python Paris", "query": "python", **over}
    return await repo.create_search(db, org_id=org_id, values=values)


async def test_defaults_and_bounds(db_session: AsyncSession):
    org = await _org(db_session, "a")
    search = await _search(db_session, org)
    assert (search.min_score, search.daily_limit, search.enabled) == (70, 5, True)

    for bad in ({"min_score": 101}, {"daily_limit": 0}, {"daily_limit": 11}):
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await _search(db_session, org, **bad)


async def test_a_job_is_seen_once_per_org_and_other_orgs_see_nothing(
    db_session: AsyncSession,
):
    ada, bob = await _org(db_session, "ada"), await _org(db_session, "bob")
    s_ada, s_bob = await _search(db_session, ada), await _search(db_session, bob)

    first = await repo.add_result(
        db_session,
        org_id=ada,
        search_id=s_ada.id,
        source="ft",
        external_id="X1",
        job_id=None,
        score=82.0,
        status="new",
    )
    again = await repo.add_result(
        db_session,
        org_id=ada,
        search_id=s_ada.id,
        source="ft",
        external_id="X1",
        job_id=None,
        score=10.0,
        status="skipped",
    )
    other_org = await repo.add_result(
        db_session,
        org_id=bob,
        search_id=s_bob.id,
        source="ft",
        external_id="X1",
        job_id=None,
        score=50.0,
        status="new",
    )

    assert (first, again, other_org) == (True, False, True)
    assert await repo.seen_external_ids(
        db_session, org_id=ada, source="ft", external_ids=["X1", "X2"]
    ) == {"X1"}
    assert (
        await repo.seen_external_ids(
            db_session, org_id=bob, source="ft", external_ids=["X2"]
        )
        == set()
    )
    mine = (
        (
            await db_session.execute(
                select(RadarResult.score).where(
                    RadarResult.org_id == ada, RadarResult.external_id == "X1"
                )
            )
        )
        .scalars()
        .all()
    )
    assert mine == [82.0]  # the second write did not overwrite it
    assert await repo.get_search(db_session, org_id=bob, search_id=s_ada.id) is None


async def test_deleting_a_search_removes_its_results_and_runs(db_session: AsyncSession):
    org = await _org(db_session, "c")
    search = await _search(db_session, org)
    await repo.add_result(
        db_session,
        org_id=org,
        search_id=search.id,
        source="ft",
        external_id="Y1",
        job_id=None,
        score=70.0,
        status="new",
    )
    await repo.start_run(db_session, org_id=org, search_id=search.id)

    await repo.delete_search(db_session, search)

    assert (await db_session.execute(select(RadarResult))).scalars().all() == []
    assert (
        await db_session.execute(text("SELECT count(*) FROM radar_runs"))
    ).scalar_one() == 0
