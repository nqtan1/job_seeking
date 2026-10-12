"""Spelling and grammar corrections the user can accept one by one.

The model only *proposes* ``(wrong, right, reason, context)``. Code decides what is shown, so
the user is never offered a change to words they did not write:

* ``wrong`` must be found in the text at a word boundary. Matching ignores typography the
  model normalises away (curly vs straight apostrophes, non-breaking spaces, zero-width
  characters, decomposed accents) and maps back to the original text.
* A repeated word is located with the model's ``context`` fragment; if that cannot pin one
  occurrence, the proposal is dropped rather than guessing (a wrong guess would "fix" a
  correct word).
* A correction fixes a word or a short phrase; rewrites, changed digits and stray invisible
  characters are dropped.

Offsets are UTF-16 code units, what the browser's ``String.slice`` uses. No FastAPI or
database imports.
"""

import html
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from recruitai.modules.letters.schemas import RawSpellIssue, SpellIssue, SpellItem

MAX_ISSUES = 40
_MAX_WRONG_CHARS = 80  # a span, not a rewritten sentence
_MAX_WORD_DELTA = 2
_MAX_REASON_CHARS = 160
_MIN_SIMILARITY = 0.6  # a fix keeps most letters; a rewrite does not
_SHORT = 6  # short words are judged more loosely (a/à, ou/où, et/est)
_SHORT_SIMILARITY = 0.5
_WORD_CHAR = re.compile(r"\w", re.UNICODE)

_SPACES = frozenset("      ")
_INVISIBLE = frozenset("\u200b‌‍⁠﻿­")
_QUOTES = {"’": "'", "‘": "'", "ʼ": "'", "“": '"', "”": '"'}
_EXOTIC = _SPACES | _INVISIBLE  # not allowed to appear in a correction out of nowhere


@dataclass(frozen=True)
class Folded:
    """``text`` with typography folded, and where each of its characters came from."""

    text: str
    starts: list[int]  # original index where normalised char i starts
    ends: list[int]  # ... and where it ends


def fold(text: str) -> Folded:
    """NFC + straight quotes + plain spaces, invisible characters removed. Decomposed accents
    are composed per base+marks cluster so offsets can still be mapped back."""
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        while j < n and unicodedata.combining(text[j]):
            j += 1
        for ch in unicodedata.normalize("NFC", text[i:j]):
            if ch in _INVISIBLE:
                continue
            out.append(_QUOTES.get(ch, " " if ch in _SPACES else ch))
            starts.append(i)
            ends.append(j)
        i = j
    return Folded("".join(out), starts, ends)


def _fold_str(text: str) -> str:
    return fold(text).text


def _clean(text: str) -> str:
    """Model output as plain text: no HTML entities, NFC, no control/format characters."""
    text = unicodedata.normalize("NFC", html.unescape(text))
    return "".join(
        ch
        for ch in text
        if ch in _EXOTIC or unicodedata.category(ch) not in {"Cc", "Cf"} or ch == "\n"
    )


def _is_word_char(ch: str) -> bool:
    return bool(_WORD_CHAR.match(ch))


def _occurrences(text: str, needle: str) -> list[int]:
    """Start of every occurrence of ``needle`` that is not inside a longer word ("a" must not
    match inside "table")."""
    found: list[int] = []
    pos = text.find(needle)
    while pos != -1:
        end = pos + len(needle)
        glued_left = (
            pos > 0 and _is_word_char(text[pos - 1]) and _is_word_char(needle[0])
        )
        glued_right = (
            end < len(text) and _is_word_char(text[end]) and _is_word_char(needle[-1])
        )
        if not glued_left and not glued_right:
            found.append(pos)
        pos = text.find(needle, pos + 1)
    return found


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _plausible(wrong: str, right: str) -> bool:
    """A correction fixes a word or a short phrase; it never rewrites or changes a number."""
    if not wrong.strip() or not right.strip() or wrong == right:
        return False
    if len(wrong) > _MAX_WRONG_CHARS or len(right) > len(wrong) * 3 + 20:
        return False
    if abs(len(wrong.split()) - len(right.split())) > _MAX_WORD_DELTA:
        return False
    if re.findall(r"\d+", wrong) != re.findall(r"\d+", right):
        return False  # "2019" -> "2024" is a different fact, not a typo
    if _strip_accents(wrong) == _strip_accents(right):
        return True  # accents / capitalisation only
    ratio = SequenceMatcher(None, wrong.lower(), right.lower()).ratio()
    return ratio >= (_SHORT_SIMILARITY if len(wrong) < _SHORT else _MIN_SIMILARITY)


def _utf16(text: str, upto: int) -> int:
    """Length in UTF-16 code units of ``text[:upto]`` (JS string indexes)."""
    return len(text[:upto].encode("utf-16-le")) // 2


def _pick(
    spots: list[int], after: int, context: str, folded: str, wrong_len: int
) -> int | None:
    """Which occurrence the model meant: the one inside its ``context`` fragment; failing
    that, the only one. Never a guess between several."""
    spots = [p for p in spots if p >= after]
    if context:
        at = folded.find(context)
        while at != -1:
            inside = [
                p for p in spots if at <= p and p + wrong_len <= at + len(context)
            ]
            if inside:
                return inside[0]
            at = folded.find(context, at + 1)
    return spots[0] if len(spots) == 1 else None


def validate(items: list[SpellItem], found: list[RawSpellIssue]) -> list[SpellIssue]:
    """The model's proposals that really apply to the given texts, in reading order,
    non-overlapping, at most ``MAX_ISSUES``."""
    originals = {i.key: i.text for i in items}
    folded = {i.key: fold(i.text) for i in items}
    cursor: dict[tuple[str, str], int] = {}
    issues: list[SpellIssue] = []
    for raw in found:
        text, norm = originals.get(raw.key), folded.get(raw.key)
        if text is None or norm is None:
            continue
        wrong = _fold_str(_clean(raw.wrong))
        right = _clean(raw.right)
        if not wrong or not _plausible(wrong, _fold_str(right)):
            continue
        spots = _occurrences(norm.text, wrong)
        start = _pick(
            spots,
            cursor.get((raw.key, wrong), 0),
            _fold_str(_clean(raw.context)),
            norm.text,
            len(wrong),
        )
        if start is None:
            continue
        end = start + len(wrong)
        o_start, o_end = norm.starts[start], norm.ends[end - 1]
        span = text[o_start:o_end]
        # A correction may not smuggle in an exotic space or invisible character.
        if any(c in _EXOTIC and c not in span for c in right):
            continue
        cursor[(raw.key, wrong)] = end
        issues.append(
            SpellIssue(
                key=raw.key,
                start=_utf16(text, o_start),
                end=_utf16(text, o_end),
                wrong=span,
                right=right,
                reason=_clean(raw.reason).strip()[:_MAX_REASON_CHARS],
            )
        )
    order = {i.key: n for n, i in enumerate(items)}
    issues.sort(key=lambda i: (order[i.key], i.start))
    kept: list[SpellIssue] = []
    for issue in issues:
        previous = kept[-1] if kept else None
        if previous and previous.key == issue.key and issue.start < previous.end:
            continue  # overlapping suggestions: keep the first
        kept.append(issue)
    return kept[:MAX_ISSUES]
