from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "dev", "staging", "prod"]
    firebase_auth_emulator_host: str | None = None

    @model_validator(mode="after")
    def _forbid_emulator_in_prod(self) -> Self:
        if self.env == "prod" and self.firebase_auth_emulator_host:
            raise ValueError(
                "FIREBASE_AUTH_EMULATOR_HOST must not be set when ENV=prod"
            )
        return self
