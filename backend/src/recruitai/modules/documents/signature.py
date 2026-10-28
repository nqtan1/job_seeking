"""Signature image processing (ADR 0030). Pure: bytes in, bytes out, no DB or storage.

Any accepted upload (PNG, JPEG, first page of a PDF) becomes ONE transparent RGBA PNG: only the
ink stays, trimmed to its bounding box, at most ``MAX_SIDE_PX`` on a side. SVG never reaches the
server (the browser converts it to PNG), so it is rejected like any unknown type.
"""

import io
import threading
from dataclasses import dataclass

import pypdfium2  # type: ignore[import-untyped]
from PIL import Image, ImageFilter, ImageOps

from recruitai.core.errors import ValidationFailed
from recruitai.modules.documents.signature_spec import (
    MAX_SIDE_PX,
    SIDEWAYS_RATIO,
    Issue,
    placement_issues,
    recommended_width_mm,
)

MAX_PIXELS = 25_000_000  # decoded size cap, checked from the header before any decoding
WORK_SIDE_PX = (
    3200  # processing size: bigger than the output so a small signature on a big scan
)
# keeps its detail through the trim
MAX_PDF_PAGES = 20
PDF_RENDER_SIDE_PX = 3000
BLANK_INK_RATIO = 0.002
_INK_ALPHA = 40  # alpha above this counts as ink (bounding box, ink ratio)
_pdfium_lock = threading.Lock()  # pdfium is not thread-safe

_BAD_TYPE = "Unsupported or unrecognized file type."
_BAD_FILE = "The file could not be read as an image."


@dataclass(frozen=True)
class Analysis:
    width_px: int
    height_px: int
    aspect: float
    ink_ratio: float


def _open(data: bytes) -> Image.Image:
    """Decode a PNG/JPEG with the bomb guards; the result is loaded, RGBA-ready and upright."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise ValidationFailed("The image is too large.")
        img.load()
        return ImageOps.exif_transpose(img)  # also drops the EXIF block
    except ValidationFailed:
        raise
    except Exception as exc:
        raise ValidationFailed(_BAD_FILE) from exc


def _render_pdf(data: bytes) -> Image.Image:
    try:
        with _pdfium_lock:
            pdf = pypdfium2.PdfDocument(data)
            try:
                if len(pdf) < 1 or len(pdf) > MAX_PDF_PAGES:
                    raise ValidationFailed("The PDF must have 1 to 20 pages.")
                page = pdf[0]
                width, height = page.get_size()
                if (
                    width < 1
                    or height < 1
                    or max(width, height) / min(width, height) > 50
                ):
                    raise ValidationFailed(_BAD_FILE)
                scale = PDF_RENDER_SIDE_PX / max(width, height)
                rendered: Image.Image = page.render(scale=scale).to_pil().copy()
                return rendered
            finally:
                pdf.close()
    except ValidationFailed:
        raise
    except Exception as exc:
        raise ValidationFailed(_BAD_FILE) from exc


def _has_alpha(img: Image.Image) -> bool:
    if img.mode != "RGBA":
        return False
    return any(img.getchannel("A").histogram()[:250])


def _channel_percentile(img: Image.Image, fraction: float) -> tuple[int, ...]:
    out = []
    for hist in (img.getchannel(i).histogram() for i in range(3)):
        target, seen = fraction * sum(hist), 0
        for value, count in enumerate(hist):
            seen += count
            if seen >= target:
                out.append(value)
                break
    return tuple(out)


def _remove_paper(img: Image.Image) -> Image.Image:
    """Opaque scan or photo -> ink with soft alpha. The paper colour (a high percentile per
    channel) is divided out, lightness becomes alpha, and the ink colour comes from the nearest
    darkest neighbours so a blue pen stays blue.
    ponytail: one global paper colour; uneven lighting (a phone photo with a shadow) leaves a
    faint haze. Upgrade: divide by a heavily blurred background estimate."""
    rgb = img.convert("RGB")
    paper = [max(c, 100) for c in _channel_percentile(rgb, 0.9)]
    bands = [
        band.point([min(255, round(v * 255 / p)) for v in range(256)])
        for band, p in zip(rgb.split(), paper, strict=True)
    ]
    norm = Image.merge("RGB", bands)
    # lightness 255 -> alpha 0; lightness <= 150 -> alpha 255; linear between, floor of noise.
    alpha = norm.convert("L").point(
        [max(0, min(255, round((245 - v) * 255 / 95))) for v in range(256)]
    )
    ink = norm.filter(ImageFilter.MinFilter(5))
    ink.putalpha(alpha)
    return ink


def _trim_and_fit(img: Image.Image) -> Image.Image:
    mask = img.getchannel("A").point(
        [0] * (_INK_ALPHA + 1) + [255] * (255 - _INK_ALPHA)
    )
    box = mask.getbbox()
    if box is not None:
        left, top, right, bottom = box
        margin = max(
            4, round(max(right - left, bottom - top) * 0.02)
        )  # of the ink, not the page
        img = img.crop(
            (
                max(0, left - margin),
                max(0, top - margin),
                min(img.width, right + margin),
                min(img.height, bottom + margin),
            )
        )
    img.thumbnail(
        (MAX_SIDE_PX, MAX_SIDE_PX), Image.Resampling.LANCZOS
    )  # never upscales
    return img


def _to_png(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)  # no metadata is carried over
    return out.getvalue()


def normalise(data: bytes) -> bytes:
    """Upload bytes -> one trimmed transparent RGBA PNG; ``ValidationFailed`` for anything else."""
    if data.startswith(b"%PDF-"):
        img = _render_pdf(data)
    elif data.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        img = _open(data)
    else:
        raise ValidationFailed(_BAD_TYPE)
    img.thumbnail((WORK_SIDE_PX, WORK_SIDE_PX), Image.Resampling.LANCZOS)
    img = img.convert("RGBA")
    return _to_png(_trim_and_fit(img if _has_alpha(img) else _remove_paper(img)))


def analyse(png: bytes) -> Analysis:
    img = _open(png).convert("RGBA")
    hist = img.getchannel("A").histogram()
    total = img.width * img.height
    return Analysis(
        width_px=img.width,
        height_px=img.height,
        aspect=img.width / img.height,
        ink_ratio=sum(hist[_INK_ALPHA + 1 :]) / total,
    )


def upload_issues(analysis: Analysis) -> list[Issue]:
    if analysis.ink_ratio < BLANK_INK_RATIO:
        return ["blank"]
    issues: list[Issue] = []
    if analysis.height_px / analysis.width_px > SIDEWAYS_RATIO:
        issues.append("sideways")
    if "low_resolution" in placement_issues(
        analysis.width_px, analysis.aspect, recommended_width_mm(analysis.aspect)
    ):
        issues.append("low_resolution")
    return issues


def rotate(png: bytes, degrees: int) -> bytes:
    """Clockwise ``degrees`` (-180..180), canvas expanded, transparent corners, re-trimmed."""
    if not -180 <= degrees <= 180:
        raise ValidationFailed("degrees must be between -180 and 180.")
    img = _open(png).convert(
        "RGBa"
    )  # premultiplied: no dark fringe from the transparent fill
    img = img.rotate(-degrees, resample=Image.Resampling.BICUBIC, expand=True)
    return _to_png(_trim_and_fit(img.convert("RGBA")))
