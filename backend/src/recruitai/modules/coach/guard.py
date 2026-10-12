"""Nothing personal leaves in a web search (F4). The model never sees the candidate's identity
(``context.identity_free``), and this check refuses a query that carries it anyway, because the
model can be talked into anything by a job posting or a web page."""

import re
import unicodedata
from typing import Any

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?\d[\s().-]*){8,}")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_WORD = re.compile(r"\w+", re.UNICODE)
MAX_QUERY_CHARS = 200


def _fold(text: str) -> str:
    """Case- and accent-insensitive: "Nguyễn" and "NGUYEN" are the same name."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def identity_tokens(personal_info: dict[str, Any] | None) -> set[str]:
    """Lower-cased words of the candidate's name, plus their email and phone, to refuse."""
    info = personal_info or {}
    tokens = {
        _fold(w) for w in _WORD.findall(str(info.get("name") or "")) if len(w) >= 3
    }
    for key in ("email", "phone", "address", "linkedin", "github", "website"):
        value = _fold(str(info.get(key) or "").strip())
        if value:
            tokens.add(value)
    return tokens


def query_problem(query: str, personal_info: dict[str, Any] | None) -> str | None:
    """Why this search query must not run, or None. Whole-query refusal, never silent editing."""
    text = query.strip()
    if not text:
        return "empty_query"
    if len(text) > MAX_QUERY_CHARS:
        return "query_too_long"
    if _EMAIL.search(text) or _PHONE.search(text) or _URL.search(text):
        return "personal_data"
    lowered = _fold(text)
    words = {_fold(w) for w in _WORD.findall(text)}
    for token in identity_tokens(personal_info):
        if token in words or (len(token) > 8 and token in lowered):
            return "personal_data"
    return None
