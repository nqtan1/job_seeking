"""letters/tasks.py pieces that need no database (P2-20): the forbidden-input check and the
Tectonic subprocess wrapper (driven by tiny fake `tectonic` scripts, never the real binary)."""

import io
import shutil
import stat
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from recruitai.modules.documents.signature_spec import fit_mm
from recruitai.modules.letters.tasks import RenderError, check_tex_allowed, compile_tex
from recruitai.modules.letters.templates import render_tex
from tests.unit.test_letters_latex import TEMPLATES, _content


@pytest.mark.parametrize(
    "tex",
    [
        r"\write18{rm -rf /}",
        r"\immediate\write18{curl evil.test}",
        r"\input{/etc/passwd}",
        r"\input{../../secret}",
        r"\include{other}",
        r"\openin5=/etc/passwd",
        r"\openout3=out.txt",
        r"\catcode`\~=0",
        r"\csname write\endcsname",
        r"^^5cwrite18{x}",  # a backslash spelled in hex
        r"\InputIfFileExists{/etc/passwd}{}{}",
        r"\directlua{os.execute('x')}",
    ],
)
def test_dangerous_commands_are_rejected_before_compiling(tex):
    with pytest.raises(RenderError) as err:
        check_tex_allowed("\\documentclass{article}\n\\begin{document}\n" + tex)
    assert err.value.code == "render_forbidden_input" and not err.value.retryable


@pytest.mark.parametrize("template", TEMPLATES)
def test_the_real_templates_pass_the_check(template):
    check_tex_allowed(render_tex(_content(), template=template, language="fr"))
    # lookalike control words are fine: \inputenc, \readme are not \input / \read
    check_tex_allowed(r"\usepackage[utf8]{inputenc} \textbf{readme}")


def _fake_tectonic(tmp_path: Path, body: str) -> str:
    script = tmp_path / "tectonic"
    # argv: -X compile --untrusted --outdir DIR FILE
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


async def test_compile_returns_the_pdf_and_passes_the_untrusted_flag(tmp_path):
    args_file = tmp_path / "args.txt"
    binary = _fake_tectonic(
        tmp_path,
        f'echo "$@" > {args_file}\nprintf "%%PDF-1.4 fake" > "$5/letter.pdf"\n',
    )
    pdf = await compile_tex("\\documentclass{article}", binary=binary)
    assert pdf.startswith(b"%PDF-")
    assert "--untrusted" in args_file.read_text()


async def test_compile_failure_timeout_and_missing_binary_are_safe_retryable_errors(
    tmp_path,
):
    failing = _fake_tectonic(tmp_path, "echo secret detail >&2\nexit 1\n")
    with pytest.raises(RenderError) as err:
        await compile_tex("x", binary=failing)
    assert (err.value.code, err.value.retryable) == ("render_failed", True)
    assert "secret" not in str(err.value)

    no_output = _fake_tectonic(tmp_path, "exit 0\n")  # exit 0 but no PDF
    with pytest.raises(RenderError) as err:
        await compile_tex("x", binary=no_output)
    assert err.value.code == "render_failed"

    slow = _fake_tectonic(tmp_path, "sleep 30\n")
    with pytest.raises(RenderError) as err:
        await compile_tex("x", binary=slow, timeout_s=0.3)
    assert err.value.code == "render_timeout"

    with pytest.raises(RenderError) as err:
        await compile_tex("x", binary=str(tmp_path / "does-not-exist"))
    assert (err.value.code, err.value.retryable) == ("render_unavailable", False)


LINE = r"\includegraphics[width=1.0mm,height=1.0mm,keepaspectratio]{signature.png}"


@pytest.mark.parametrize("template", TEMPLATES)
def test_signature_picture_sits_above_the_name_and_only_when_set(template):
    plain = render_tex(_content(), template=template, language="fr")
    # fit_mm: 200 mm is clamped to 70 mm, then to the 28 mm block height (aspect 5 -> 14 mm)
    signed = render_tex(
        _content(), template=template, language="fr", signature=fit_mm(5.0, 200)
    )
    assert "includegraphics" not in plain and r"\usepackage{graphicx}" in plain
    assert "[width=70.0mm,height=14.0mm,keepaspectratio]{signature.png}" in signed
    typed_name = signed.rindex("Lucas Martel")
    assert signed.index("includegraphics") < typed_name
    assert typed_name - signed.index("includegraphics") < 200  # right before the name
    check_tex_allowed(signed, templated=True)
    with pytest.raises(RenderError):  # the same line is refused in raw mode
        check_tex_allowed(signed)


def test_a_tall_signature_is_shrunk_to_the_block_height():
    tex = render_tex(
        _content(), template="classic", language="en", signature=fit_mm(2.0, 70)
    )
    assert "width=56.0mm,height=28.0mm" in tex


@pytest.mark.parametrize(
    "tex",
    [
        r"\includegraphics{/etc/passwd}", LINE, r"\pdfximage{x.png}",
        r"\pdfliteral{x}", r"\pdfrefximage1",
    ],
)  # fmt: skip
def test_raw_override_may_not_read_files_or_inject_pdf(tex):
    with pytest.raises(RenderError) as err:
        check_tex_allowed(r"\begin{document}" + tex)
    assert err.value.code == "render_forbidden_input"


def test_user_text_cannot_forge_the_signature_line_in_templated_output():
    tex = render_tex(_content(closing=LINE), template="classic", language="en")
    assert LINE not in tex
    check_tex_allowed(tex, templated=True)  # escaped text is harmless, not matched
    # and a raw tail after our line is still checked
    with pytest.raises(RenderError):
        check_tex_allowed(LINE + r"\includegraphics{/etc/passwd}", templated=True)


async def test_a_real_compile_embeds_the_signature_under_untrusted():
    if shutil.which("tectonic") is None:
        pytest.skip("tectonic is not installed")
    image = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    ImageDraw.Draw(image).line(
        [(5, 90), (150, 10), (295, 80)], fill=(10, 10, 120, 255), width=4
    )
    buf = io.BytesIO()
    image.save(buf, "PNG")
    tex = render_tex(
        _content(), template="lettre_fr", language="vi", signature=fit_mm(3.0, 40)
    )
    check_tex_allowed(tex, templated=True)
    pdf = await compile_tex(
        tex, timeout_s=300, assets={"signature.png": buf.getvalue()}
    )
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1 and len(reader.pages[0].images) == 1
