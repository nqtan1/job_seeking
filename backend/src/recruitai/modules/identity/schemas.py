"""Response DTOs for the identity module (ARCHITECTURE.md §4.2, walkthrough §3 Flow A)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None


class OnboardingOut(BaseModel):
    has_profile: bool


class MeResponse(BaseModel):
    user: UserOut
    active_org_id: UUID
    onboarding: OnboardingOut
    is_admin: bool = False
    email_reminders: bool = True


class AdminUserOut(BaseModel):
    """Metadata only: no CV, letter or job content ever reaches the admin screens."""

    id: UUID
    email: str
    display_name: str | None
    created_at: datetime
    last_active_at: datetime | None
    blocked: bool


class AdminUserList(BaseModel):
    items: list[AdminUserOut]
    total: int


class UserCounts(BaseModel):
    total: int
    new_7d: int
    new_30d: int
    active_7d: int
    active_30d: int


class DayCount(BaseModel):
    day: str
    count: int


class ContentCounts(BaseModel):
    profiles: int
    jobs: int
    letters: int
    applications: int


class AiUsage(BaseModel):
    feature: str
    calls: int
    errors: int
    input_tokens: int
    output_tokens: int


class AdminStats(BaseModel):
    users: UserCounts
    signups_by_day: list[DayCount]
    content: ContentCounts
    applications_by_status: dict[str, int]
    ai_last_30d: list[AiUsage]


class PreferencesIn(BaseModel):
    email_reminders: bool


class AiFeatureOut(BaseModel):
    feature: str
    provider: str
    model: str | None
    default: str
    overridden: bool
    prompt_version: str | None
    calls: int
    errors: int
    avg_latency_ms: int
    p95_latency_ms: int
    input_tokens: int
    output_tokens: int


class AiChangeOut(BaseModel):
    feature: str
    old_value: str | None
    new_value: str | None
    at: datetime


class AiConsoleOut(BaseModel):
    features: list[AiFeatureOut]
    allowed_models: dict[str, list[str]]
    changes: list[AiChangeOut]


class AiOverrideIn(BaseModel):
    provider: str = Field(..., max_length=20)
    model: str = Field(..., max_length=100)
