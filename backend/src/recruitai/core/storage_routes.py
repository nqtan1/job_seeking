"""Dev-only signed-download route for ``LocalStorage`` (split from ``core/storage.py`` so
services never import FastAPI). Never mounted when ``ENV=prod`` — see ``main.py``.

Resolves storage via ``Depends(get_storage_dependency)`` at request time, like any other
route, rather than closing over one instance at app-construction time — otherwise a test's
``dependency_overrides`` override would never reach this route, and it would silently keep
using the process-wide singleton instead of the fake.
"""

from typing import Annotated
from uuid import UUID

import firebase_admin
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.auth import get_current_user, get_firebase_app
from recruitai.core.db import get_db
from recruitai.core.errors import NotFound, Unauthorized
from recruitai.core.filenames import content_disposition, safe_filename
from recruitai.core.storage import (
    LocalStorage,
    ObjectNotFound,
    Storage,
    get_storage_dependency,
)
from recruitai.core.tenancy import get_org_context

router = APIRouter()

# The dev store keeps only bytes, so sniff the type (the upload allowlist: PDF, PNG, JPEG, text).
# A wrong type (octet-stream) makes browsers download instead of showing the file inline.
_MAGIC = (
    (b"%PDF", "application/pdf"),
    (b"\x89PNG", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def _media_type(data: bytes) -> str:
    return next((m for magic, m in _MAGIC if data.startswith(magic)), "text/plain")


async def _caller_org(
    request: Request,
    app: Annotated[firebase_admin.App, Depends(get_firebase_app)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UUID | None:
    """The caller's org when the request is authenticated, else None. A signed link works
    without a login (a browser ``<a href>`` sends none), like a GCS signed URL."""
    authorization = request.headers.get("authorization")
    if authorization is None:
        return None
    user = await get_current_user(app, authorization)
    ctx = await get_org_context(user, db, request.headers.get("x-org-id"))
    return ctx.org_id


@router.get("/_dev/storage/{key:path}")
async def download(
    key: str,
    exp: int,
    sig: str,
    storage: Annotated[Storage, Depends(get_storage_dependency)],
    caller_org: Annotated[UUID | None, Depends(_caller_org)],
    name: str | None = None,
    dl: int = 0,
) -> Response:
    if not isinstance(storage, LocalStorage) or not storage.verify_signature(
        key, exp, sig
    ):
        raise Unauthorized("Invalid or expired signed URL.")
    # Defense in depth: a valid link is not enough when the request says who is asking.
    # Org B holding org A's link still gets a plain 404 (never "forbidden": no existence leak).
    if caller_org is not None and not key.startswith(f"orgs/{caller_org}/"):
        raise NotFound("Object not found.")
    try:
        data = await storage.get(key)
    except ObjectNotFound:
        raise NotFound("Object not found.") from None
    return Response(
        content=data,
        media_type=_media_type(data),
        headers={
            "X-Content-Type-Options": "nosniff",
            **(
                {
                    "Content-Disposition": content_disposition(
                        safe_filename(name),
                        attachment=bool(dl),
                    )
                }
                if name
                else {}
            ),
        },
    )
