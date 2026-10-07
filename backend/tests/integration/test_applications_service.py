"""applications service against the real DB (P2-26)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.modules.applications import repository, service
from recruitai.modules.applications.schemas import (
    TRANSITIONS,
    ApplicationIn,
    ApplicationUpdate,
)
from recruitai.modules.jobs import repository as jobs_repo
from tests.integration.test_letters_service import _tenant
from tests.unit.test_jobs_parser import blank_job

TODAY = datetime.now(UTC).date()


async def test_create_from_a_job_fills_company_and_title_and_records_the_first_event(
    db_session: AsyncSession,
):
    org, _ = await _tenant(db_session, "a")
    job = await jobs_repo.add(
        db_session, org_id=org.id, source="manual", external_id=None,
        info=blank_job(title="Dev Python"),
    )  # fmt: skip

    app = await service.create_application(
        db_session, org_id=org.id, data=ApplicationIn(job_id=job.id, source="linkedin")
    )

    assert (app.company_name, app.job_title, app.job_id) == (
        "Acme",
        "Dev Python",
        job.id,
    )
    assert (app.status, app.applied_at) == ("to_apply", None)
    events = await service.list_events(db_session, org_id=org.id, application_id=app.id)
    assert [(e.from_status, e.to_status) for e in events] == [(None, "to_apply")]

    manual = await service.create_application(
        db_session,
        org_id=org.id,
        data=ApplicationIn(company_name="Initech", status="applied"),
    )
    assert (manual.job_id, manual.job_title, manual.applied_at) == (None, None, TODAY)
    explicit = await service.create_application(
        db_session,
        org_id=org.id,
        data=ApplicationIn(
            company_name="X", status="applied", applied_at=date(2026, 9, 1)
        ),
    )
    assert explicit.applied_at == date(2026, 9, 1)  # a date the user gave is kept


async def test_every_status_pair_is_either_a_recorded_move_or_a_clean_refusal(
    db_session: AsyncSession,
):
    org, _ = await _tenant(db_session, "a")
    statuses = list(TRANSITIONS)
    for start in statuses:
        for target in statuses:
            app = await repository.create(
                db_session, org_id=org.id, job_id=None, company_name="Acme",
                job_title=None, source="other", status=start, applied_at=None, notes=None,
            )  # fmt: skip
            before = len(
                await service.list_events(
                    db_session, org_id=org.id, application_id=app.id
                )
            )
            if target in TRANSITIONS[start]:
                moved = await service.change_status(
                    db_session, org_id=org.id, application_id=app.id,
                    to_status=target, note="  merci  ",
                )  # fmt: skip
                assert moved.status == target
                events = await service.list_events(
                    db_session, org_id=org.id, application_id=app.id
                )
                assert len(events) == before + 1
                last = events[-1]
                assert (last.from_status, last.to_status, last.note) == (
                    start,
                    target,
                    "merci",
                )
            else:
                with pytest.raises(ValidationFailed) as err:
                    await service.change_status(
                        db_session,
                        org_id=org.id,
                        application_id=app.id,
                        to_status=target,
                    )
                assert start in err.value.detail and target in err.value.detail
                unchanged = await service.get_application(
                    db_session, org_id=org.id, application_id=app.id
                )
                assert unchanged.status == start
                events = await service.list_events(
                    db_session, org_id=org.id, application_id=app.id
                )
                assert len(events) == before  # a refused move leaves no trace


async def test_moving_to_applied_sets_the_date_once(db_session: AsyncSession):
    org, _ = await _tenant(db_session, "a")
    app = await service.create_application(
        db_session, org_id=org.id, data=ApplicationIn(company_name="Acme")
    )
    app = await service.change_status(
        db_session, org_id=org.id, application_id=app.id, to_status="applied"
    )
    assert app.applied_at == TODAY
    app = await service.update_application(
        db_session, org_id=org.id, application_id=app.id,
        changes=ApplicationUpdate(applied_at=date(2026, 9, 1)),
    )  # fmt: skip
    app = await service.change_status(
        db_session, org_id=org.id, application_id=app.id, to_status="in_review"
    )
    assert app.applied_at == date(2026, 9, 1)  # later moves never overwrite it


async def test_update_list_filter_and_delete(db_session: AsyncSession):
    org, _ = await _tenant(db_session, "a")
    a = await service.create_application(
        db_session, org_id=org.id, data=ApplicationIn(company_name="A", notes="first")
    )
    b = await service.create_application(
        db_session,
        org_id=org.id,
        data=ApplicationIn(company_name="B", status="applied"),
    )

    updated = await service.update_application(
        db_session, org_id=org.id, application_id=a.id,
        changes=ApplicationUpdate(notes=None, job_title="Dev", source="indeed"),
    )  # fmt: skip
    assert (updated.notes, updated.job_title, updated.source, updated.company_name) == (
        None, "Dev", "indeed", "A",
    )  # fmt: skip

    everything = await service.list_applications(db_session, org_id=org.id)
    assert [x.id for x in everything] == [b.id, a.id]  # newest first
    only_applied = await service.list_applications(
        db_session, org_id=org.id, status="applied"
    )
    assert [x.id for x in only_applied] == [b.id]

    await service.delete_application(db_session, org_id=org.id, application_id=a.id)
    assert [
        x.id for x in await service.list_applications(db_session, org_id=org.id)
    ] == [b.id]
    with pytest.raises(NotFound):
        await service.get_application(db_session, org_id=org.id, application_id=a.id)


async def test_other_orgs_see_nothing_and_cannot_use_a_foreign_job(
    db_session: AsyncSession,
):
    a, job_a = await _tenant(db_session, "a")
    b, _ = await _tenant(db_session, "b")
    app = await service.create_application(
        db_session, org_id=a.id, data=ApplicationIn(company_name="Acme")
    )

    with pytest.raises(NotFound):
        await service.get_application(db_session, org_id=b.id, application_id=app.id)
    with pytest.raises(NotFound):
        await service.update_application(
            db_session,
            org_id=b.id,
            application_id=app.id,
            changes=ApplicationUpdate(notes="x"),
        )
    with pytest.raises(NotFound):
        await service.change_status(
            db_session, org_id=b.id, application_id=app.id, to_status="applied"
        )
    with pytest.raises(NotFound):
        await service.list_events(db_session, org_id=b.id, application_id=app.id)
    with pytest.raises(NotFound):
        await service.delete_application(db_session, org_id=b.id, application_id=app.id)
    with pytest.raises(NotFound):  # B cannot link an application to A's job
        await service.create_application(
            db_session, org_id=b.id, data=ApplicationIn(job_id=job_a.id)
        )
    assert await service.list_applications(db_session, org_id=b.id) == []
    untouched = await service.get_application(
        db_session, org_id=a.id, application_id=app.id
    )
    assert untouched.status == "to_apply"
