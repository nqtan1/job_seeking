"""Compiles every letter template, in French and English, with Tectonic, offline (ADR 0010).

Run inside the worker image with no network: ``docker run --network none <image> python
/app/docker/render_check.py``. It uses the production code path (``render_tex`` +
``compile_tex``), so it proves the templates only need the pre-warmed package bundle, that
hostile text cannot break out of a letter, and that ``--untrusted`` is accepted by the
installed Tectonic. Exits non-zero on any failure.
"""

import asyncio
import sys

from recruitai.modules.letters.schemas import Header, LetterContent, Recipient
from recruitai.modules.letters.tasks import compile_tex
from recruitai.modules.letters.templates import render_tex

TEMPLATES = ["classic", "modern", "compact", "lettre_fr"]
HOSTILE = r"\end{document}\write18{touch /tmp/pwned} 100% & $5 #1 _x_ {y} ~z ^w \\"


def content(text: str) -> LetterContent:
    return LetterContent(
        header=Header(
            name=text, email="ada@example.test", phone="0102030405",
            address="12 rue de la Paix, 69001 Lyon", date="2026-10-02",
        ),
        recipient=Recipient(company=f"Acme & Fils {text}"),
        subject=f"Candidature Développeur Python (H/F) {text}",
        salutation="Madame, Monsieur,",
        opening=f"Je vous écris pour ... œuvre « à propos » {text}",
        body=["Chez Brightwave, j'ai livré 25 correctifs.", text],
        closing="Veuillez agréer mes salutations distinguées.",
        signature="Ada Lovelace",
    )  # fmt: skip


async def main() -> int:
    failures = 0
    for template in TEMPLATES:
        for language in ("fr", "en"):
            for label, text in (("plain", "Ada Lovelace"), ("hostile", HOSTILE)):
                tex = render_tex(content(text), template=template, language=language)  # type: ignore[arg-type]
                try:
                    pdf = await compile_tex(tex, timeout_s=120)
                    ok = pdf.startswith(b"%PDF-")
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    print(f"  error: {type(exc).__name__} {getattr(exc, 'code', '')}")
                print(f"{'ok  ' if ok else 'FAIL'} {template}/{language}/{label}")
                failures += not ok
    return failures


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
