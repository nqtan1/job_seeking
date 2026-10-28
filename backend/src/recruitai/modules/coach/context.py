"""What goes into the coach's prompt, bounded (design §2). The candidate's identity is left out so
it cannot reach a web search. Character caps stand in for tokens (about 4 characters each)."""

from typing import Any

from recruitai.ai.text import compact_json

JOB_CHARS = 10_000
PROFILE_CHARS = 6_000
FIT_CHARS = 4_000
TOOL_RESULT_CHARS = 12_000
_TRUNCATED = " […truncated]"
_IDENTITY_KEYS = ("personal_info", "references")


def fence(text: str) -> str:
    """Untrusted text goes between our markers: it must not be able to close one or open another."""
    return text.replace("<", "‹").replace(">", "›")


def identity_free(profile: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in profile.items() if k not in _IDENTITY_KEYS}


def clip(text: str, cap: int) -> tuple[str, bool]:
    if len(text) <= cap:
        return text, False
    return text[: cap - len(_TRUNCATED)] + _TRUNCATED, True


def job_json(data: dict[str, Any], cap: int) -> tuple[str, bool]:
    """Fixed fields stay whole; the free-text description gives way first."""
    text = compact_json(data)
    if len(text) <= cap:
        return text, False
    body = data.get("job_description_text")
    if isinstance(body, str):
        keep = max(0, len(body) - (len(text) - cap) - len(_TRUNCATED))
        text = compact_json({**data, "job_description_text": body[:keep] + _TRUNCATED})
    return clip(text, cap)[0], True


def json_block(data: Any, cap: int) -> tuple[str, bool]:
    return clip(compact_json(data), cap)
