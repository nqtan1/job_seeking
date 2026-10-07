import os
from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

Provider = Literal["gemini", "qwen"]


# Every agent config.yaml must route (the prompt id before "@").
AGENTS = ("cv_extract", "job_extract", "fit", "letter", "letter_assist", "coach")


class AgentLLM(BaseModel):
    """One agent's entry in config.yaml. ``model`` left out = the provider's default."""

    provider: Provider
    model: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Precedence: real env vars > .env (secrets) > config.yaml (non-secret settings) > defaults.
    # CONFIG_FILE overrides the path ("" disables it; tests do that).
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_file = os.environ.get("CONFIG_FILE", "config.yaml")
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file or None),
            file_secret_settings,
        )

    env: Literal["local", "dev", "staging", "prod"]
    firebase_auth_emulator_host: str | None = None
    firebase_project_id: str

    # Postgres. Both the API and the worker connect directly (no transaction-mode
    # pooler): Procrastinate needs LISTEN/NOTIFY. Connection budget per process is
    # db_pool_size + db_max_overflow, so total = instances * that; keep it under the
    # server's max_connections.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_s: int = 30
    db_pool_recycle_s: int = 1800
    db_statement_timeout_ms: int = 30_000
    db_idle_in_transaction_timeout_ms: int = 60_000

    # Storage (core/storage.py). LocalStorage is dev/test only — a container can be killed
    # at any time, so prod must never write files to local disk (ARCHITECTURE.md rule 1).
    storage_backend: Literal["local", "gcs"] = "local"
    local_storage_root: str = "./.data"
    local_storage_signing_secret: str = "dev-only-signing-secret-do-not-use-in-prod"
    gcs_bucket: str | None = None

    # AI (ai/gateway.py, ai/gemini.py, ai/qwen.py). Which provider and model each agent
    # uses comes from config.yaml (`agents:`); URLs and keys come from .env. Gemini's auth mode is
    # detected from the env (see ``gemini_auth``). Only Gemini on Vertex is allowed in prod
    # (ADR 0009, ADR 0015).
    google_genai_use_vertexai: bool = False
    gemini_api_key: str | None = None
    google_cloud_project: str | None = None
    google_cloud_location: str | None = None
    gemini_flash_lite: str = "gemini-2.5-flash-lite"
    gemini_flash: str = "gemini-2.5-flash"
    ai_daily_quota_per_user: int = 50
    ai_call_timeout_s: float = 30.0
    ai_max_retries: int = 3
    # config.yaml `agents:`; every name in AGENTS must be present.
    agents: dict[str, AgentLLM] = {}
    qwen_base_url: str | None = None
    qwen_api_key: str | None = None
    qwen_model_name: str | None = None
    # Optional vision model, used when a request carries an image. Falls back to the QWEN_* trio.
    qwen_vl_base_url: str | None = None
    # QWEN_VL_KEY is the name the owner's .env already uses.
    qwen_vl_api_key: str | None = Field(
        None, validation_alias=AliasChoices("qwen_vl_api_key", "qwen_vl_key")
    )
    qwen_vl_model_name: str | None = None

    # France Travail job search (modules/jobs/providers). Optional: search says "not configured" without them.
    france_travail_client_id: str | None = None
    france_travail_client_secret: str | None = None
    france_travail_api_url: str | None = None

    # Transactional email (core/email.py). "fake" records instead of sending: the dev/test default.
    email_backend: Literal["fake", "brevo"] = "fake"
    brevo_api_key: str | None = None
    email_sender_address: str = "no-reply@recruitai.example"
    email_sender_name: str = "RecruitAI"

    # Platform admins: verified emails, e.g. ADMIN_EMAILS='["me@example.com"]'. Everyone else who
    # signs up is a normal user with a personal org (core/auth.py ``is_admin``).
    admin_emails: list[str] = []

    # Kill switch for the scheduled job radar (ADR 0021); the API's "Run now" is separate.
    radar_enabled: bool = True

    # App Check (core/app_check.py). Only ENV=local may disable enforcement (no emulator
    # setup friction in local dev) — prod can never turn it off.
    app_check_enforced: bool = True

    def provider_for(self, feature: str) -> Provider:
        return self.agents[feature.split("@")[0]].provider

    def agent_model(self, feature: str | None, default: str) -> str:
        agent = self.agents.get(feature.split("@")[0]) if feature else None
        return (agent and agent.model) or default

    @property
    def gemini_auth(self) -> Literal["vertex", "api_key"]:
        """Prod is always Vertex. Elsewhere: GOOGLE_GENAI_USE_VERTEXAI (the google-genai
        SDK's own switch) wins, else an API key if present, else Vertex."""
        if (
            self.env == "prod"
            or self.google_genai_use_vertexai
            or not self.gemini_api_key
        ):
            return "vertex"
        return "api_key"

    @model_validator(mode="after")
    def _brevo_needs_its_key(self) -> Self:
        if self.email_backend == "brevo" and not self.brevo_api_key:
            raise ValueError("BREVO_API_KEY is required when EMAIL_BACKEND=brevo")
        return self

    @model_validator(mode="after")
    def _forbid_emulator_in_prod(self) -> Self:
        if self.env == "prod" and self.firebase_auth_emulator_host:
            raise ValueError(
                "FIREBASE_AUTH_EMULATOR_HOST must not be set when ENV=prod"
            )
        return self

    @model_validator(mode="after")
    def _forbid_local_storage_in_prod(self) -> Self:
        if self.env == "prod" and self.storage_backend == "local":
            raise ValueError("STORAGE_BACKEND must be 'gcs' when ENV=prod")
        return self

    @model_validator(mode="after")
    def _every_agent_is_routed(self) -> Self:
        if missing := [a for a in AGENTS if a not in self.agents]:
            raise ValueError(f"config.yaml `agents:` is missing {missing}")
        return self

    @model_validator(mode="after")
    def _forbid_qwen_in_prod(self) -> Self:
        if self.env == "prod" and any(
            a.provider == "qwen" for a in self.agents.values()
        ):
            raise ValueError(
                "provider 'qwen' is dev/self-hosted only; ENV=prod requires 'gemini' (Vertex)"
            )
        return self

    @model_validator(mode="after")
    def _forbid_disabling_app_check_in_prod(self) -> Self:
        if self.env == "prod" and not self.app_check_enforced:
            raise ValueError("APP_CHECK_ENFORCED cannot be false when ENV=prod")
        return self


@lru_cache
def get_settings() -> Settings:
    """FastAPI dependency: one cached instance per process. Env vars are read once at
    process start in this codebase (see tests/conftest.py), so caching is safe; a test
    that truly needs a different Settings overrides this dependency, not the environment."""
    return Settings()  # type: ignore[call-arg]  # fields are populated from the environment
