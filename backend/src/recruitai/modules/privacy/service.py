"""Data export (GDPR Art. 20) and, later, account deletion and retention sweeps.

Each module exports its own org-scoped rows through its ``service.export_data``; this module
only assembles them. The ZIP is built completely before anything is stored, and the document
row is created only after the object is stored: a failure at any point leaves no document, so
there is never a download link to an incomplete archive."""

import json
import tempfile
import zipfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.ai import usage
from recruitai.core.email import EmailSender
from recruitai.core.errors import UpstreamUnavailable
from recruitai.core.export import rows_as_dicts
from recruitai.core.storage import Storage
from recruitai.core.tasks import enqueue, find_queued
from recruitai.modules.applications import service as applications
from recruitai.modules.candidates import service as candidates
from recruitai.modules.coach import service as coach
from recruitai.modules.documents import service as documents
from recruitai.modules.identity import service as identity
from recruitai.modules.jobs import service as jobs
from recruitai.modules.letters import service as letters
from recruitai.modules.matching import service as matching
from recruitai.modules.radar import service as radar

EXPORT_TASK_KIND = "privacy.export_user_data"
EXPORT_MAX_BYTES = 256 * 1024 * 1024
_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


EXPORT_TASK = (
    "privacy:export_user_data"  # registered by the worker (namespace "privacy")
)


async def request_export(db: AsyncSession, *, org_id: UUID, user_id: UUID) -> UUID:
    """Queue the export (atomic with its ``task_runs`` row, ADR 0017). Asking again while one
    is still queued returns that task: exports are heavy and must not pile up."""
    pending = await find_queued(db, org_id=org_id, kind=EXPORT_TASK_KIND)
    if pending is not None:
        return pending
    task_run_id = await enqueue(
        db,
        task=EXPORT_TASK,
        org_id=org_id,
        kind=EXPORT_TASK_KIND,
        task_kwargs={"org_id": str(org_id), "user_id": str(user_id)},
    )
    await db.commit()
    return task_run_id


async def build_export(
    db: AsyncSession,
    storage: Storage,
    *,
    org_id: UUID,
    user_id: UUID,
    now: datetime | None = None,
) -> UUID:
    """Build the caller's ZIP and store it as a ``documents`` row of kind ``export``.
    Returns the document id. The caller commits."""
    data: dict[str, Any] = {
        "account": await identity.export_data(db, org_id=org_id, user_id=user_id)
    }
    for module in (
        candidates,
        jobs,
        matching,
        letters,
        applications,
        coach,
        documents,
        radar,
    ):
        data.update(await module.export_data(db, org_id=org_id))
    data["ai_usage"] = rows_as_dicts(await usage.export_rows(db, org_id=org_id))

    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    missing_files: list[str] = []
    with tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024) as spool:
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in data.items():
                archive.writestr(f"{name}.json", _dump(content))
            async for document, blob in documents.iter_files(
                db, storage, org_id=org_id
            ):
                path = f"files/{document.kind}/{document.id}{_EXTENSIONS.get(document.mime, '')}"
                if blob is None:
                    missing_files.append(path)
                else:
                    archive.writestr(path, blob)
            archive.writestr(
                "manifest.json",
                _dump(
                    {
                        "generated_at": (now or datetime.now(UTC)).isoformat(),
                        "counts": counts,
                        "missing_files": missing_files,
                    }
                ),
            )
        spool.seek(0)
        payload = spool.read()

    document = await documents.store_generated(
        db,
        storage,
        org_id=org_id,
        kind="export",
        data=payload,
        mime="application/zip",
        max_bytes=EXPORT_MAX_BYTES,
    )
    # The previous export is replaced, not accumulated (a stale archive is personal data too),
    # but only now that the new one is safely stored: a failure above leaves the old one intact.
    await documents.delete_generated(
        db, storage, org_id=org_id, kind="export", keep=document.id
    )
    return document.id


async def delete_account(
    db: AsyncSession,
    storage: Storage,
    *,
    user_id: UUID,
    delete_identity: Callable[[], Awaitable[None]],
) -> None:
    """Delete the account for good, in an order that is safe to retry after a failure:

    1. storage objects first: if the DB step then fails the user still exists and can retry
       (a row pointing at a missing file is harmless; a file nobody can reach is not);
    2. database rows and queued jobs, committed at once;
    3. the sign-in identity last (Firebase): if that fails only an empty identity is left,
       and retrying deletes it.
    ``delete_identity`` is passed in so this service never imports Firebase."""
    org_ids = await identity.owned_org_ids(db, user_id=user_id)
    for org_id in org_ids:
        await storage.delete_prefix(f"orgs/{org_id}/")
    await identity.delete_account_rows(db, user_id=user_id, org_ids=org_ids)
    await db.commit()
    await delete_identity()


# ---- Retention sweeps (ARCHITECTURE.md §11.2) -------------------------------------------------
# Each takes ``now`` so tests drive a fake clock, and each only ever touches rows past its own
# threshold. None of them touches ``letters``: a draft letter is an ordinary letter, never swept.

INACTIVE_AFTER = timedelta(days=730)  # 24 months of no sign-in
FIRST_WARNING_AT = timedelta(days=700)  # 30 days before deletion
FINAL_WARNING_AT = timedelta(days=723)  # 7 days before deletion
MIN_WARNING_LEAD = timedelta(days=7)  # a warning is always followed by >= 7 days
AI_CALLS_KEPT = timedelta(days=395)  # 13 months
EXPORT_KEPT = timedelta(hours=24)
RADAR_RUNS_KEPT = timedelta(days=90)
SWEEP_BATCH = 200


async def sweep_ai_calls(db: AsyncSession, *, now: datetime) -> int:
    deleted = await usage.delete_older_than(db, cutoff=now - AI_CALLS_KEPT)
    await db.commit()
    return deleted


async def sweep_radar_runs(db: AsyncSession, *, now: datetime) -> int:
    return await radar.sweep_old_runs(db, cutoff=now - RADAR_RUNS_KEPT)


async def sweep_exports(db: AsyncSession, storage: Storage, *, now: datetime) -> int:
    return await documents.sweep_older_than(
        db, storage, kind="export", cutoff=now - EXPORT_KEPT
    )


async def sweep_job_search_cache(db: AsyncSession, *, now: datetime) -> int:
    return await jobs.sweep_cache(db, now=now)


async def sweep_inactive_accounts(
    db: AsyncSession,
    storage: Storage,
    email: EmailSender,
    *,
    now: datetime,
    delete_identity_for: Callable[[str], Callable[[], Awaitable[None]]],
) -> dict[str, int]:
    """Warn at 30 and 7 days before the 24-month mark, then delete: **never delete without a
    warning sent first, and never right after one.**

    A warning only counts if it was sent *after* the user's last activity (so coming back
    cancels everything, with no reset step). Deletion needs the 7-day warning to have been sent
    at least 7 days ago, so a late sweep (an outage) delays the deletion instead of skipping the
    warning. A failed email leaves the user unmarked: the next run tries again."""
    result = {"warned": 0, "deleted": 0}
    users = await identity.inactive_users(
        db, idle_since=now - FIRST_WARNING_AT, limit=SWEEP_BATCH
    )
    for user in users:
        idle = now - user.last_active
        warned = user.warned_at
        final_sent = (
            warned is not None and warned >= user.last_active + FINAL_WARNING_AT
        )
        if (
            idle >= INACTIVE_AFTER
            and final_sent
            and warned is not None
            and now - warned >= MIN_WARNING_LEAD
        ):
            await delete_account(
                db,
                storage,
                user_id=user.id,
                delete_identity=delete_identity_for(user.firebase_uid),
            )
            result["deleted"] += 1
            continue
        first_sent = (
            warned is not None and warned >= user.last_active + FIRST_WARNING_AT
        )
        if idle >= FINAL_WARNING_AT and not final_sent:
            due = max(user.last_active + INACTIVE_AFTER, now + MIN_WARNING_LEAD)
        elif idle < FINAL_WARNING_AT and not first_sent:
            due = user.last_active + INACTIVE_AFTER
        else:
            continue  # already warned for this stage (or waiting out the 7 days)
        try:
            await email.send(
                user.email,
                "inactivity_warning",
                {
                    "days_left": max((due - now).days, 0),
                    "delete_on": due.date().isoformat(),
                },
            )
        except UpstreamUnavailable:
            continue  # not marked as warned: tried again on the next run
        await identity.mark_warned(db, user_id=user.id, at=now)
        await db.commit()
        result["warned"] += 1
    return result
