"""Admin overrides of the model each AI feature uses (ADR 0022, stage B).

``config.yaml`` stays the default; a row in ``ai_settings`` replaces one feature's provider and
model without a deploy. Only models on an allowlist are accepted and ``ENV=prod`` stays Vertex
only. Every change is audited (who, old → new) and reversible by removing the override. Prompts
are not touched here: they stay in code.

Gateways read the effective settings through a short in-process cache (``TTL_S``), so another
instance picks a change up within that time. No FastAPI imports."""

import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from recruitai.config import AGENTS, AgentLLM, Provider, Settings
from recruitai.core.db import Base
from recruitai.core.errors import NotFound, ValidationFailed
from recruitai.core.ids import new_id

TTL_S = 30.0
RETRY_AFTER_S = (
    5.0  # after a failed read, try again this soon (the defaults apply meanwhile)
)
# Models an admin may pick. Qwen (dev / self-hosted) accepts only the configured model name.
GEMINI_MODELS = ("gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro")


class AiSetting(Base):
    __tablename__ = "ai_settings"

    feature: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AiSettingChange(Base):
    """Audit trail: values are ``provider/model`` text, NULL meaning "the config.yaml default"."""

    __tablename__ = "ai_setting_changes"
    __table_args__ = (Index("ix_ai_setting_changes_at", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    feature: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(String)
    new_value: Mapped[str | None] = mapped_column(String)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


logger = logging.getLogger(__name__)

_cache: tuple[float, dict[str, AgentLLM]] | None = None


def invalidate() -> None:
    global _cache
    _cache = None


async def load(db: AsyncSession) -> dict[str, AgentLLM]:
    """The active overrides, cached for ``TTL_S`` seconds."""
    global _cache
    if _cache is not None and time.monotonic() - _cache[0] < TTL_S:
        return _cache[1]
    try:
        async with (
            db.begin_nested()
        ):  # a failed read must not poison the caller's transaction
            rows = (await db.execute(select(AiSetting))).scalars().all()
    except Exception as exc:  # noqa: BLE001  (e.g. migration not applied yet: use config.yaml)
        logger.error(
            "ai overrides unavailable", extra={"error_type": type(exc).__name__}
        )
        _cache = (time.monotonic() - TTL_S + RETRY_AFTER_S, {})
        return {}
    found = {r.feature: AgentLLM(provider=r.provider, model=r.model) for r in rows}  # type: ignore[arg-type]
    _cache = (time.monotonic(), found)
    return found


async def effective_settings(settings: Settings, db: AsyncSession) -> Settings:
    """``settings`` with the admin overrides applied on top of ``config.yaml``."""
    overrides = await load(db)
    if not overrides:
        return settings
    return settings.model_copy(update={"agents": {**settings.agents, **overrides}})


def allowed_models(settings: Settings) -> dict[Provider, list[str]]:
    allowed: dict[Provider, list[str]] = {"gemini": list(GEMINI_MODELS)}
    if settings.env != "prod" and settings.qwen_model_name:
        allowed["qwen"] = [settings.qwen_model_name]
    return allowed


def _validate(settings: Settings, feature: str, provider: str, model: str) -> None:
    if feature not in AGENTS:
        raise NotFound("Unknown AI feature.")
    allowed: dict[str, list[str]] = {k: v for k, v in allowed_models(settings).items()}
    if model not in allowed.get(provider, []):
        raise ValidationFailed("That provider and model are not allowed here.")


async def set_override(
    db: AsyncSession,
    settings: Settings,
    *,
    feature: str,
    provider: str,
    model: str,
    admin_user_id: uuid.UUID | None,
) -> None:
    _validate(settings, feature, provider, model)
    current = (
        await db.execute(select(AiSetting).where(AiSetting.feature == feature))
    ).scalar_one_or_none()
    default = settings.agents[feature]
    old = (
        f"{current.provider}/{current.model}"
        if current
        else f"{default.provider}/{default.model}"
    )
    if current is None:
        db.add(
            AiSetting(
                feature=feature,
                provider=provider,
                model=model,
                updated_by=admin_user_id,
            )
        )
    else:
        current.provider, current.model = provider, model
        current.updated_by = admin_user_id
        current.updated_at = datetime.now(UTC)
    db.add(
        AiSettingChange(
            feature=feature,
            old_value=old,
            new_value=f"{provider}/{model}",
            changed_by=admin_user_id,
        )
    )
    await db.commit()
    invalidate()


async def clear_override(
    db: AsyncSession, *, feature: str, admin_user_id: uuid.UUID | None
) -> None:
    """Back to the ``config.yaml`` default."""
    if feature not in AGENTS:
        raise NotFound("Unknown AI feature.")
    current = (
        await db.execute(select(AiSetting).where(AiSetting.feature == feature))
    ).scalar_one_or_none()
    if current is None:
        return
    db.add(
        AiSettingChange(
            feature=feature,
            old_value=f"{current.provider}/{current.model}",
            new_value=None,
            changed_by=admin_user_id,
        )
    )
    await db.execute(delete(AiSetting).where(AiSetting.feature == feature))
    await db.commit()
    invalidate()


async def recent_changes(db: AsyncSession, *, limit: int = 20) -> list[AiSettingChange]:
    rows = await db.execute(
        select(AiSettingChange).order_by(AiSettingChange.at.desc()).limit(limit)
    )
    return list(rows.scalars())
