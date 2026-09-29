from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "dev", "staging", "prod"]
    firebase_auth_emulator_host: str | None = None

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

    @model_validator(mode="after")
    def _forbid_emulator_in_prod(self) -> Self:
        if self.env == "prod" and self.firebase_auth_emulator_host:
            raise ValueError(
                "FIREBASE_AUTH_EMULATOR_HOST must not be set when ENV=prod"
            )
        return self
