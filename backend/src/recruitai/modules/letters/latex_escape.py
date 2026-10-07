"""The one place user text becomes LaTeX-safe (ADR 0010).

Every string that reaches a template goes through ``latex_escape``; ``escape_value`` applies it
recursively to the whole content, so a template author cannot forget it. Escaping is a single
pass over the characters (a regex substitution), so the braces *introduced* by an escape
(``\\textbackslash{}``) are never escaped again.
"""

import re
from typing import Any

_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_SPECIAL_RE = re.compile("[" + re.escape("".join(_SPECIALS)) + "]")
# C0 controls other than tab/newline: the engine chokes on them and they carry no meaning.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def latex_escape(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    return _SPECIAL_RE.sub(lambda m: _SPECIALS[m.group(0)], text)


def escape_value(value: Any) -> Any:
    """``latex_escape`` every string inside nested dicts/lists; other types pass through."""
    if isinstance(value, str):
        return latex_escape(value)
    if isinstance(value, dict):
        return {k: escape_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [escape_value(v) for v in value]
    return value
