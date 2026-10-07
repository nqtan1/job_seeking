"""Simultaneous status changes on one application (P2-28, real connections)."""

import asyncio
from itertools import pairwise
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from recruitai.core.auth import CurrentUser
from recruitai.core.errors import ValidationFailed
from recruitai.core.tenancy import get_org_context
from recruitai.modules.applications import service
from recruitai.modules.applications.schemas import ApplicationIn, ApplicationUpdate
from tests.fixtures.db import purge_tenant


async def test_two_simultaneous_moves_cannot_both_pass_validation(
    db_engine: AsyncEngine,
):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        ctx = await get_org_context(
            CurrentUser(firebase_uid=f"uid-{uuid4().hex[:8]}", email="h@example.test"),
            session,
            x_org_id=None,
        )
        app = await service.create_application(
            session,
            org_id=ctx.org_id,
            data=ApplicationIn(company_name="Acme", status="applied"),
        )

    async def move(to_status: str) -> str:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            try:
                await service.change_status(
                    session,
                    org_id=ctx.org_id,
                    application_id=app.id,
                    to_status=to_status,  # type: ignore[arg-type]
                )
            except ValidationFailed:
                return "refused"
            return "moved"

    async def edit() -> None:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await service.update_application(
                session, org_id=ctx.org_id, application_id=app.id,
                changes=ApplicationUpdate(notes="edited meanwhile"),
            )  # fmt: skip

    try:
        # offer -> rejected is legal, but a second "offer" after the first is not (offer -> offer),
        # and "rejected" after "rejected" is not either: exactly one of each pair wins.
        results = await asyncio.gather(
            move("offer"), move("offer"), move("rejected"), edit()
        )
        outcomes = results[:3]
        assert outcomes.count("moved") >= 1 and outcomes.count("refused") >= 1
        async with AsyncSession(db_engine) as session:
            final = await service.get_application(
                session, org_id=ctx.org_id, application_id=app.id
            )
            events = await service.list_events(
                session, org_id=ctx.org_id, application_id=app.id
            )
        assert final.notes == "edited meanwhile"  # the concurrent edit was not lost
        # every accepted move left exactly one event, and the chain of events is consistent
        assert len(events) == 1 + outcomes.count("moved")
        for earlier, later in pairwise(events):
            assert later.from_status == earlier.to_status
        assert events[-1].to_status == final.status
    finally:
        await purge_tenant(db_engine, org_id=ctx.org_id, user_id=ctx.user_id)
