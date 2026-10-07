"""Turn ORM rows into plain JSON-safe dicts for the data export (GDPR Art. 20).

Generic on purpose: every column of the row, nothing computed, so the export can never
silently omit a field a module adds later."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value  # str, int, float, bool, None, and JSONB dicts/lists are already JSON


def row_as_dict(row: object) -> dict[str, Any]:
    mapper = inspect(row).mapper  # type: ignore[union-attr]
    return {a.key: _json_safe(getattr(row, a.key)) for a in mapper.column_attrs}


def rows_as_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [row_as_dict(r) for r in rows]
