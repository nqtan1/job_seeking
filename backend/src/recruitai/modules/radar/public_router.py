"""The one no-session endpoint of the radar module: the e-mailed "stop radars" link (ADR 0024).
Kept apart from ``router.py`` so everything in that file stays session-authenticated."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.config import Settings, get_settings
from recruitai.core.db import get_db
from recruitai.core.errors import ValidationFailed, problem_responses
from recruitai.core.ratelimit import limit_public
from recruitai.modules.radar import links, service

router = APIRouter(prefix="/api/public", tags=["radar"])


class LinkIn(BaseModel):
    token: str


class LinkInvalid(ValidationFailed):
    code = "link_invalid"
    default_detail = "This link is invalid or has expired."


_link_limit = limit_public("radar_link", limit=60)


@router.post(
    "/radar-link", status_code=204, responses=problem_responses(ValidationFailed)
)
async def radar_link(
    body: LinkIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Withdraw radar consent from an e-mailed link. POST only (mail scanners prefetch GETs);
    the token is the only credential and buys exactly this one action. It reads nothing, returns
    nothing, signs nobody in; the answer does not depend on whether the account still exists."""
    claims = (
        links.verify(settings.radar_link_secret, body.token)
        if settings.radar_link_secret
        else None
    )
    if claims is None:
        # Rejected before the rate limit (so the call below is not a Depends): junk costs one
        # HMAC and cannot use up the quota that genuine "stop" links need.
        raise LinkInvalid()
    _link_limit()  # bounds the database work a *valid* (replayed) link can cause
    await service.apply_link(
        db, claims, policy_version=settings.radar_consent_policy_version
    )
    return Response(status_code=204)
