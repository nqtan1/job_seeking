"""Human-friendly download names ("Motivation letter - Ada Lovelace - Acme.pdf").

Names are display-only: storage keys never come from them (``core/storage.object_key``).
"""

import re
from urllib.parse import quote

_UNSAFE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|;]+')


def safe_filename(*parts: str | None, ext: str = "") -> str:
    """Join the non-empty parts with " - ", drop characters that break headers or file systems
    (accents and other letters are kept), cap the length."""
    text = " - ".join(
        p for p in (_UNSAFE.sub(" ", p or "").strip() for p in parts) if p
    )
    text = re.sub(r"\s+", " ", text)[:100].strip(" .") or "Document"
    return f"{text}.{ext}" if ext else text


def content_disposition(filename: str, *, attachment: bool) -> str:
    """``inline`` shows it in the browser; ``attachment`` saves it. The ASCII fallback keeps old
    browsers working, ``filename*`` carries the real (UTF-8) name."""
    ascii_name = filename.encode("ascii", "ignore").decode() or "download"
    kind = "attachment" if attachment else "inline"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
