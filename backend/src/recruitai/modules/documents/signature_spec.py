"""The signature contract shared by the upload endpoints, the letter renderer and the web app:
the physical limits of the signature block on a letter and the arithmetic that fits an image
into them. Pure: no I/O, no Pillow.

A signature sits in a block above the printed name. It is judged by its PRINTED size in mm, not
by pixels: too small to read, too big for the block (it would collide with the text above or run
past the margin), or too few pixels for that size (blurry on paper).
"""

from typing import Literal

# Issues the user can see (the web app translates the code).
Issue = Literal[
    "blank",  # (almost) no ink found: an empty or unreadable file
    "sideways",  # taller than wide: most likely scanned rotated
    "low_resolution",  # too few pixels for a sharp print at the chosen width
    "too_small",  # printed so small it cannot be read
    "too_big",  # printed bigger than the block
]

MIN_WIDTH_MM = 20  # narrowest width the user can pick
MAX_WIDTH_MM = 70  # widest (the text column is ~160 mm)
MAX_HEIGHT_MM = 28  # tallest: the block above the name
MIN_HEIGHT_MM = 8  # shorter than this is unreadable whatever the width
READABLE_WIDTH_MM = 25  # below this the strokes are too thin to read
MIN_DPI = 200  # below this a print looks blurry
MAX_SIDE_PX = 1600  # stored images are never bigger than this on either side
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
SIDEWAYS_RATIO = 1.2  # height / width above this is "sideways"
MM_PER_INCH = 25.4


def fit_mm(aspect: float, width_mm: float) -> tuple[float, float]:
    """The size the renderer really prints for a requested width: the width is clamped to
    ``[MIN_WIDTH_MM, MAX_WIDTH_MM]``, then shrunk (aspect kept) until the height fits
    ``MAX_HEIGHT_MM``. ``aspect`` is width / height of the stored image. This is the automatic
    fix applied at render time, so a PDF can never overflow its block."""
    width = min(max(width_mm, MIN_WIDTH_MM), MAX_WIDTH_MM)
    if width / aspect > MAX_HEIGHT_MM:
        width = MAX_HEIGHT_MM * aspect
    return width, width / aspect


def recommended_width_mm(aspect: float) -> int:
    """The largest width that still fits the block (never below the readable minimum)."""
    return round(max(fit_mm(aspect, MAX_WIDTH_MM)[0], READABLE_WIDTH_MM))


def placement_issues(width_px: int, aspect: float, width_mm: float) -> list[Issue]:
    """What is wrong with printing this image at ``width_mm`` (before the automatic fix)."""
    height_mm = width_mm / aspect
    issues: list[Issue] = []
    if width_mm < READABLE_WIDTH_MM or height_mm < MIN_HEIGHT_MM:
        issues.append("too_small")
    if width_mm > MAX_WIDTH_MM or height_mm > MAX_HEIGHT_MM:
        issues.append("too_big")
    printed = fit_mm(aspect, width_mm)[0]
    if width_px / (printed / MM_PER_INCH) < MIN_DPI:
        issues.append("low_resolution")
    return issues
