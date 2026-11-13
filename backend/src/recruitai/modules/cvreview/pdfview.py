"""Where each block sits in the ORIGINAL PDF, so the user sees what and where in their own file.
``layout`` matches block text against the PDF text layer (whitespace and case ignored) and returns
one box per printed line, as fractions of the page; ``render_page`` draws a page as PNG. A block
that cannot be found (edited, hyphenated across lines, odd reading order) simply has no box."""

import io
import unicodedata
from typing import Any

import pypdfium2

from recruitai.core.pdfium import lock
from recruitai.modules.cvreview.blocks import MAX_PAGES

RENDER_SIDE_PX = 1600
MIN_NEEDLE = 3


def _fold(ch: str) -> str:
    return unicodedata.normalize(
        "NFKC", ch
    ).casefold()  # 'ﬁ' -> 'fi', same as the quote folding


def _chars(
    pdf: Any,
) -> tuple[str, list[tuple[int, tuple[float, float, float, float]]], list[float]]:
    """(text without spaces, [(page, l, t, r, b as page fractions)] per char, h/w per page)."""
    hay, where, ratios = [], [], []
    for p in range(min(len(pdf), MAX_PAGES)):
        page = pdf[p]
        w, h = page.get_size()
        ratios.append(h / w)
        if page.get_rotation():  # boxes would need turning: show the text view only
            return "", [], []
        tp = page.get_textpage()
        for i in range(tp.count_chars()):
            ch = tp.get_text_range(i, 1)
            if not ch or ch.isspace():
                continue
            l, b, r, t = tp.get_charbox(i)
            if r <= l or t <= b:
                continue
            for f in _fold(ch):
                hay.append(f)
                where.append((p, (l / w, 1 - t / h, r / w, 1 - b / h)))
    return "".join(hay), where, ratios


def layout(data: bytes, blocks: list[tuple[str, str]]) -> dict[str, Any] | None:
    """{"ratios": [h/w per page], "boxes": {block id: [{p, x, y, w, h, s, e}]}} where ``s..e`` is
    the span of the block text on that line. None if the file cannot be read."""
    try:
        with lock:
            pdf = pypdfium2.PdfDocument(data)
            try:
                hay, where, ratios = _chars(pdf)
            finally:
                pdf.close()
    except Exception:  # noqa: BLE001  (a broken PDF just has no overlay)
        return None
    boxes: dict[str, list[dict[str, Any]]] = {}
    cursor = 0
    for bid, text in blocks:
        needle, at = [], []
        for k, ch in enumerate(text):
            if not ch.isspace():
                for f in _fold(ch):
                    needle.append(f)
                    at.append(k)
        n = "".join(needle)
        if len(n) < MIN_NEEDLE:
            continue
        pos = hay.find(n, cursor)
        in_order = pos >= 0
        if not in_order:
            pos = hay.find(n)
        if pos < 0:
            continue
        if in_order:
            cursor = pos + len(n)
        lines: list[dict[str, Any]] = []
        for m, k in enumerate(at):
            p, (l, t, r, b) = where[pos + m]
            cur = lines[-1] if lines else None
            if (
                cur
                and cur["p"] == p
                and abs((t + b) - (cur["y"] * 2 + cur["h"])) < cur["h"]
            ):
                right = max(cur["x"] + cur["w"], r)
                bottom = max(cur["y"] + cur["h"], b)
                cur["x"], cur["y"] = min(cur["x"], l), min(cur["y"], t)
                cur["w"], cur["h"], cur["e"] = (
                    right - cur["x"],
                    bottom - cur["y"],
                    k + 1,
                )
            else:
                lines.append(
                    {"p": p, "x": l, "y": t, "w": r - l, "h": b - t, "s": k, "e": k + 1}
                )
        boxes[bid] = lines
    return {"ratios": ratios, "boxes": boxes}


def render_page(data: bytes, page: int) -> bytes | None:
    """PNG of page ``page`` (1-based), at most RENDER_SIDE_PX on the long side; None if absent."""
    with lock:
        pdf = pypdfium2.PdfDocument(data)
        try:
            if not 1 <= page <= min(len(pdf), MAX_PAGES):
                return None
            pg = pdf[page - 1]
            w, h = pg.get_size()
            img = pg.render(scale=RENDER_SIDE_PX / max(w, h)).to_pil()
            out = io.BytesIO()
            img.save(out, "PNG")
            return out.getvalue()
        finally:
            pdf.close()
