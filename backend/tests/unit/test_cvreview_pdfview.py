"""The overlay finds each block's printed lines in a real (tiny) PDF and renders its pages."""

from recruitai.modules.cvreview import pdfview


def _pdf(lines: list[str]) -> bytes:
    """A one-page PDF (Helvetica 12) with one text line per entry, top to bottom."""
    ops = (
        "BT /F1 12 Tf 14 TL 72 720 Td "
        + " T* ".join(f"({t}) Tj" for t in lines)
        + " ET"
    )
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        f"<< /Length {len(ops)} >> stream\n{ops}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    return (
        out
        + f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )


def test_blocks_are_found_in_order_and_edited_ones_are_not():
    data = _pdf(
        ["Built a billing API", "Cut latency by 40 percent", "Python and Redis"]
    )
    out = pdfview.layout(
        data,
        [
            ("b1", "Built a billing API"),
            ("b2", "Cut  latency by 40 percent"),  # whitespace and case do not matter
            ("b3", "I rewrote this line"),  # not in the file
            ("b4", "python and redis"),
        ],
    )
    assert out and out["ratios"] == [792 / 612]
    boxes = out["boxes"]
    assert set(boxes) == {"b1", "b2", "b4"}
    ys = [boxes[b][0]["y"] for b in ("b1", "b2", "b4")]
    assert ys == sorted(ys) and 0 < ys[0] < ys[-1] < 1  # top to bottom, as fractions
    line = boxes["b1"][0]
    assert (line["s"], line["e"], line["p"]) == (0, 19, 0)
    assert (
        abs(line["x"] - 72 / 612) < 0.005 and line["w"] > 0.1
    )  # starts at the 72 pt margin


def test_page_renders_as_png_and_bad_input_is_harmless():
    assert pdfview.render_page(_pdf(["x y z"]), 1)[:4] == b"\x89PNG"
    assert pdfview.render_page(_pdf(["x y z"]), 2) is None
    assert pdfview.layout(b"not a pdf", [("b1", "whatever")]) is None
