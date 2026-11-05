"""Shared FastAPI dependency for every agents router."""

from typing import Annotated

from fastapi import Depends

from recruitai.config import Settings, get_settings
from recruitai.core.errors import NotFound


def require_enabled(settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Off means the feature does not exist: a plain 404, so nothing leaks about it."""
    if not settings.helpers_enabled:
        raise NotFound("Not found.")
