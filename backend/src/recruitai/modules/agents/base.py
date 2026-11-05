"""The base of every request model of the module."""

from typing import Any

from pydantic import BaseModel, model_validator


def _has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(k) or _has_nul(v) for k, v in value.items())
    if isinstance(value, list | tuple):
        return any(_has_nul(v) for v in value)
    return False


class Strict(BaseModel):
    """Base of every request model. Postgres text and JSONB cannot hold NUL, so a payload that
    carries one anywhere is refused at the edge (a 422) instead of failing on write (a 500)."""

    @model_validator(mode="before")
    @classmethod
    def _no_nul(cls, data: Any) -> Any:
        if _has_nul(data):
            raise ValueError("NUL characters are not allowed")
        return data
