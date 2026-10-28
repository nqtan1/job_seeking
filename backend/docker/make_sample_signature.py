"""Regenerates sample-signature.png, the tiny picture the Docker pre-warm compile includes
(Pillow is a dev dependency; the PNG is committed): `uv run python docker/make_sample_signature.py`."""

from pathlib import Path

from PIL import Image, ImageDraw

image = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
ImageDraw.Draw(image).line(
    [(4, 34), (30, 6), (60, 32), (116, 10)], fill=(20, 20, 110, 255), width=3
)
image.save(Path(__file__).with_name("sample-signature.png"), optimize=True)
