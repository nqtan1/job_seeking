"""Signature image processing and the placement arithmetic (ADR 0030), on images drawn in code."""

import io

import pytest
from PIL import Image, ImageDraw

from recruitai.core.errors import ValidationFailed
from recruitai.modules.documents import signature
from recruitai.modules.documents.signature_spec import (
    MAX_HEIGHT_MM,
    MAX_SIDE_PX,
    MAX_WIDTH_MM,
    MIN_WIDTH_MM,
    fit_mm,
    placement_issues,
    recommended_width_mm,
)

BLUE = (20, 40, 200)


def _encode(img: Image.Image, fmt: str) -> bytes:
    out = io.BytesIO()
    img.save(out, format=fmt)
    return out.getvalue()


def scan(fmt="PNG", size=(1200, 800), ink=BLUE) -> bytes:
    """A blue stroke on off-white paper, like a scanner or phone produces."""
    img = Image.new("RGB", size, (245, 243, 238))
    draw = ImageDraw.Draw(img)
    draw.line([(400, 300), (600, 500), (800, 350)], fill=ink, width=10)
    return _encode(img, fmt)


def pdf_bytes() -> bytes:
    stream = b"2 w 0 0 1 RG 20 20 m 280 180 l S"
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R>>",
        b"<</Length %d>>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    body, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%s\nendobj\n" % (i, obj)
    xref = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    body += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return body + b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (
        len(objs) + 1,
        xref,
    )


def load(png: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG" and img.mode == "RGBA"
    return img


@pytest.mark.parametrize(
    "source", [scan("JPEG"), scan("PNG"), pdf_bytes()], ids=["jpeg", "png", "pdf"]
)
def test_a_scan_becomes_trimmed_transparent_ink_that_keeps_its_colour(source):
    img = load(signature.normalise(source))

    assert max(img.size) <= MAX_SIDE_PX
    if not source.startswith(b"%PDF"):  # the PDF stroke spans its page
        assert img.width < 1000 and img.height < 600  # trimmed inside the 1200x800 page
    assert img.getpixel((0, 0))[3] == 0  # paper is gone
    opaque = [p for p in img.convert("RGBA").get_flattened_data() if p[3] > 240]
    assert opaque
    r, g, b, _ = opaque[len(opaque) // 2]
    assert b > r + 60 and b > g + 60  # blue pen stays blue


def test_real_alpha_is_kept_and_big_images_are_shrunk_never_enlarged():
    src = Image.new("RGBA", (3000, 2000), (0, 0, 0, 0))
    ImageDraw.Draw(src).rectangle((100, 100, 2900, 1900), fill=(10, 10, 10, 255))
    big = load(signature.normalise(_encode(src, "PNG")))
    assert max(big.size) == MAX_SIDE_PX
    assert big.getpixel((big.width // 2, big.height // 2)) == (10, 10, 10, 255)

    small = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ImageDraw.Draw(small).rectangle((20, 20, 180, 80), fill=(0, 0, 0, 255))
    assert max(load(signature.normalise(_encode(small, "PNG"))).size) <= 200


@pytest.mark.parametrize(
    "data",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        b"<?xml version='1.0'?><svg/>",
        b"garbage",
        b"\x89PNG\r\n\x1a\ntruncated",
        b"%PDF-1.4 not really",
    ],
)
def test_svg_and_garbage_are_rejected(data):
    with pytest.raises(ValidationFailed):
        signature.normalise(data)


def test_a_decompression_bomb_is_refused_from_its_header():
    bomb = _encode(Image.new("1", (6000, 6000)), "PNG")  # 36M px, a few KB
    assert len(bomb) < 100_000
    with pytest.raises(ValidationFailed):
        signature.normalise(bomb)


def test_issues_blank_sideways_and_low_resolution():
    blank = signature.normalise(
        _encode(Image.new("RGB", (800, 400), (250, 250, 250)), "PNG")
    )
    assert signature.upload_issues(signature.analyse(blank)) == ["blank"]

    ok = signature.analyse(signature.normalise(scan()))
    assert signature.upload_issues(ok) == []

    tall = Image.new("RGBA", (120, 300), (0, 0, 0, 0))
    ImageDraw.Draw(tall).rectangle((5, 5, 115, 295), fill=(0, 0, 0, 255))
    issues = signature.upload_issues(signature.analyse(_encode(tall, "PNG")))
    assert issues == ["sideways"]

    wide = Image.new("RGBA", (300, 100), (0, 0, 0, 0))  # 300 px over 70 mm is ~110 dpi
    ImageDraw.Draw(wide).rectangle((5, 5, 295, 95), fill=(0, 0, 0, 255))
    assert signature.upload_issues(signature.analyse(_encode(wide, "PNG"))) == [
        "low_resolution"
    ]


@pytest.mark.parametrize("degrees", [90, -90, 37])
def test_rotate_expands_trims_and_keeps_alpha(degrees):
    png = signature.normalise(scan())
    before = load(png)
    after = load(signature.rotate(png, degrees))

    assert after.getpixel((0, 0))[3] == 0
    assert max(after.size) <= MAX_SIDE_PX
    if (
        abs(degrees) == 90
    ):  # dimensions swap (the margin is re-added, so allow a few px)
        assert (
            abs(after.width - before.height) <= 8
            and abs(after.height - before.width) <= 8
        )
    else:
        assert after.size != before.size
    assert after.getchannel("A").getbbox() is not None


def test_fit_mm_clamps_and_keeps_aspect_and_placement_issues():
    assert fit_mm(2.0, 5)[0] == MIN_WIDTH_MM
    width, height = fit_mm(2.0, 500)
    assert (width, height) == (
        MAX_HEIGHT_MM * 2.0,
        MAX_HEIGHT_MM,
    )  # 70 mm would be 35 mm tall
    width, height = fit_mm(1.0, 60)  # square: the height cap wins, aspect kept
    assert height == MAX_HEIGHT_MM and width == height
    assert 25 <= recommended_width_mm(1.0) <= MAX_WIDTH_MM

    assert placement_issues(2000, 2.0, 10) == ["too_small"]
    assert "too_big" in placement_issues(2000, 2.0, 100)
    assert placement_issues(100, 2.0, 50) == ["low_resolution"]
    assert placement_issues(1600, 2.0, 50) == []
