"""Small helpers for building prompts."""

import json
from typing import Any


def compact_json(data: Any) -> str:
    """Compact, unicode-preserving JSON for putting profile/job/letter data in a prompt
    (indent and escaped accents would only cost tokens)."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
