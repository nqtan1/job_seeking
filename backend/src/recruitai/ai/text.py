"""Small helpers for building prompts and checking what a model quoted."""

import json
import unicodedata
from typing import Any


def fence(text: str) -> str:
    """Untrusted text goes between our markers: it must not be able to close one or open another."""
    return text.replace("<", "‹").replace(">", "›")


def compact_json(data: Any) -> str:
    """Compact, unicode-preserving JSON for putting profile/job/letter data in a prompt
    (indent and escaped accents would only cost tokens)."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


_PUNCT = str.maketrans("‘’“”–—", "''\"\"--")


def fold(s: str) -> tuple[str, list[tuple[int, int]]]:
    """NFKC + ASCII quotes/dashes + collapsed whitespace, with the original span of each char."""
    clusters: list[
        tuple[str, int, int]
    ] = []  # (raw, start, end): base char + its accents
    for i, c in enumerate(s):
        if clusters and (
            unicodedata.combining(c) or (c.isspace() and clusters[-1][0].isspace())
        ):
            clusters[-1] = (clusters[-1][0] + c, clusters[-1][1], i + 1)
        else:
            clusters.append((c, i, i + 1))
    text, spans = "", []
    for raw, a, b in clusters:
        f = (
            " "
            if raw.isspace()
            else unicodedata.normalize("NFKC", raw).translate(_PUNCT)
        )
        text += f
        spans += [(a, b)] * len(f)
    return text, spans


def locate(quote: str, text: str, *, min_chars: int = 8) -> str | None:
    """``quote`` as the exact passage of ``text`` it copies (unicode/whitespace-tolerant, case-
    sensitive), or None. Shorter than ``min_chars`` only counts when it is the whole text."""
    fq = fold(quote)[0].strip()
    ft, spans = fold(text)
    if not fq or (len(fq) < min_chars and fq != ft.strip()):
        return None
    i = ft.find(fq)
    return None if i < 0 else text[spans[i][0] : spans[i + len(fq) - 1][1]]
