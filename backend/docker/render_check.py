"""Compiles every letter template (fr/en, with a signature) with Tectonic, offline (ADR 0010).

Run in the worker image with ``--network none``. Proves the templates need only the pre-warmed
bundle, hostile text cannot break out, and ``--untrusted`` is accepted. Exits non-zero on failure.
"""

import asyncio
import struct
import sys
import zlib

from recruitai.modules.documents.signature_spec import fit_mm
from recruitai.modules.letters.schemas import (
    Header,
    LetterContent,
    Recipient,
    SignatureImage,
)
from recruitai.modules.letters.tasks import compile_tex
from recruitai.modules.letters.templates import render_tex

TEMPLATES = ["classic", "modern", "compact", "lettre_fr"]
HOSTILE = r"\end{document}\write18{touch /tmp/pwned} 100% & $5 #1 _x_ {y} ~z ^w \\"


def png(width: int = 300, height: int = 100) -> bytes:
    """A valid transparent RGBA PNG with a diagonal stroke (stdlib only, no file needed)."""
    rows = b""
    for y in range(height):
        row = bytearray(width * 4)
        x = width * y // height
        row[x * 4 : x * 4 + 4] = bytes((20, 20, 110, 255))
        rows += b"\x00" + bytes(row)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


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
        signature_image=SignatureImage(width_mm=45),
    )  # fmt: skip


async def main() -> int:
    failures = 0
    for template in TEMPLATES:
        for language in ("fr", "en", "vi"):
            for label, text in (("plain", "Ada Lovelace"), ("hostile", HOSTILE)):
                tex = render_tex(
                    content(text),
                    template=template,
                    language=language,  # type: ignore[arg-type]
                    signature=fit_mm(3.0, 45),
                )
                try:
                    pdf = await compile_tex(
                        tex, timeout_s=120, assets={"signature.png": png()}
                    )
                    ok = pdf.startswith(b"%PDF-")
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    print(f"  error: {type(exc).__name__} {getattr(exc, 'code', '')}")
                print(f"{'ok  ' if ok else 'FAIL'} {template}/{language}/{label}")
                failures += not ok
    return failures


if __name__ == "__main__":
    sys.exit(1 if asyncio.run(main()) else 0)
