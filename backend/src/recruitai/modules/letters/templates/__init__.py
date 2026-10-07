"""Render ``LetterContent`` to LaTeX with the Jinja templates next to this file (ADR 0010).

Jinja delimiters are ``\\VAR{..}`` / ``\\BLOCK{..}`` so template braces never clash with
LaTeX. All text is escaped in Python *before* it reaches a template (``escape_value``), so a
template can't forget to. Templates only use packages the worker image pre-warms
(``geometry``, ``fontspec`` with the bundled Latin Modern OpenType fonts, ``babel`` in French
and English): Tectonic is offline at runtime, and ``docker/sample.tex`` pre-warms exactly this
set. Fonts via ``fontspec`` (not T1 + ``inputenc``) because Tectonic is XeTeX: it reads UTF-8
directly, so ``œ``, ``’``, ``«»`` and ``€`` need a Unicode font. The ``latex_override`` mode skips this module entirely (the caller's job).
"""

from datetime import date
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from recruitai.modules.letters.latex_escape import escape_value
from recruitai.modules.letters.schemas import Language, LetterContent, Template

_LABELS = {
    "fr": {"subject": "Objet :", "babel": "french"},
    "en": {"subject": "Subject:", "babel": "english"},
}
_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]  # fmt: skip
_LINE_BREAK = " \\\\\n"  # LaTeX `\\` between the lines of an address block


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(Path(__file__).parent),
        block_start_string="\\BLOCK{",
        block_end_string="}",
        variable_start_string="\\VAR{",
        variable_end_string="}",
        comment_start_string="\\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,  # the text is escaped for LaTeX before rendering, not HTML
        undefined=StrictUndefined,  # a typo in a template fails loudly, never renders empty
        keep_trailing_newline=True,
    )


def format_date(iso: str | None, language: Language) -> str:
    """'2026-10-02' → '2 octobre 2026' / '2 October 2026'; anything unparsable is kept as is."""
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    if language == "fr":
        return f"{d.day} {_MONTHS_FR[d.month - 1]} {d.year}"
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _lines(*values: str | None) -> list[str]:
    return [v for v in values if v]


def render_tex(
    content: LetterContent, *, template: Template, language: Language
) -> str:
    c = escape_value(content.model_dump())
    header, recipient = c["header"], c["recipient"]
    date_text = format_date(content.header.date, language)  # digits and letters only
    sender = [
        header["name"],
        *_lines(header["address"], header["email"], header["phone"]),
    ]
    context = {
        "babel": _LABELS[language]["babel"],
        "labels": _LABELS[language],
        "name": header["name"],
        "contact_line": " \\textbullet{} ".join(
            _lines(header["address"], header["email"], header["phone"])
        ),
        "sender_details": _LINE_BREAK.join(sender[1:]),  # everything under the name
        "recipient_block": _LINE_BREAK.join(
            _lines(
                recipient["company"], recipient["contact_name"], recipient["address"]
            )
        ),
        "date": date_text,
        "date_line": f"Le {date_text}" if language == "fr" else date_text,
        "subject": c["subject"],
        "salutation": c["salutation"],
        "paragraphs": [c["opening"], *c["body"]],
        "closing": c["closing"],
        "signature": c["signature"],
    }
    return _env().get_template(f"{template}.tex.j2").render(context)
