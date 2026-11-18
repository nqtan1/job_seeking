"""Radar consent: grant, withdraw (also by a signed no-login link) and its history."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recruitai.core.errors import Conflict
from recruitai.modules.radar import links, repository
from recruitai.modules.radar.schemas import ConsentOut

logger = logging.getLogger(__name__)


async def consented_orgs(
    db: AsyncSession, *, org_ids: list[UUID], policy_version: str
) -> set[UUID]:
    """Orgs whose newest radar consent is a grant of the *current* policy text."""
    latest = await repository.latest_consents(db, org_ids=org_ids)
    return {
        o
        for o, c in latest.items()
        if c.event == "granted" and c.policy_version == policy_version
    }


async def get_consent(
    db: AsyncSession, *, org_id: UUID, policy_version: str
) -> ConsentOut:
    history = await repository.consent_history(db, org_id=org_id)
    state = "none"
    if history:
        latest = history[0]
        if latest.event == "withdrawn":
            state = "withdrawn"
        elif latest.policy_version == policy_version:
            state = "granted"
        else:
            state = "needs_reconsent"
    return ConsentOut.model_validate(
        {
            "state": state,
            "policy_version": policy_version,
            "history": [
                {
                    "event": c.event,
                    "at": c.at,
                    "policy_version": c.policy_version,
                    "source": c.source,
                }
                for c in history
            ],
        }
    )


async def grant_consent(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    seen_version: str,
    policy_version: str,
) -> ConsentOut:
    if seen_version != policy_version:
        raise Conflict(
            "The consent text has changed. Please read it again.",
            code="consent_version_mismatch",
        )
    await repository.add_consent(
        db,
        org_id=org_id,
        user_id=user_id,
        policy_version=policy_version,
        event="granted",
        source="ui",
    )
    await repository.release_org_searches(db, org_id=org_id, reason="consent")
    await db.commit()
    logger.info("radar_consent_granted")
    return await get_consent(db, org_id=org_id, policy_version=policy_version)


async def withdraw_consent(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    policy_version: str,
    source: str = "ui",
    now: datetime | None = None,
) -> ConsentOut:
    """Append the withdrawal and hold every radar in the same transaction: the next scheduled
    run, even one already selected, sees it."""
    latest = (await repository.latest_consents(db, org_ids=[org_id])).get(org_id)
    if latest is None or latest.event != "withdrawn":  # a replayed link adds no history
        await repository.add_consent(
            db,
            org_id=org_id,
            user_id=user_id,
            policy_version=policy_version,
            event="withdrawn",
            source=source,
        )
    await repository.hold_org_searches(
        db, org_id=org_id, reason="consent", now=now or datetime.now(UTC)
    )
    await db.commit()
    logger.info("radar_consent_withdrawn")
    return await get_consent(db, org_id=org_id, policy_version=policy_version)


async def apply_link(
    db: AsyncSession, claims: links.LinkClaims, *, policy_version: str
) -> None:
    """The one thing a signed link may do: withdraw consent. Idempotent; reads and returns
    nothing. An account deleted since the mail was sent is simply nothing to do."""
    try:
        await withdraw_consent(
            db,
            org_id=claims.org_id,
            user_id=claims.user_id,
            policy_version=policy_version,
            source="email_link",
        )
    except IntegrityError:
        await db.rollback()


def withdraw_link(secret: str, *, org_id: UUID, user_id: UUID, ttl_s: int) -> str:
    """Token for the no-login "stop radars" link (other modules go through the service)."""
    return links.sign(secret, org_id=org_id, user_id=user_id, ttl_s=ttl_s)
