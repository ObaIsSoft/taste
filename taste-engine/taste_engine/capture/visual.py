"""Image helpers used to decide when a page is visible and when it has stopped moving."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

_THUMB = (240, 150)  # comparison resolution: enough to see a page change, cheap to diff


def thumbnail(png: bytes) -> Image.Image:
    with Image.open(BytesIO(png)) as image:
        return image.convert("L").resize(_THUMB)


def spread(thumb: Image.Image) -> float:
    """Grey-level standard deviation; near zero for a blank frame."""
    return ImageStat.Stat(thumb).stddev[0]


def difference(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute grey-level difference between two thumbnails."""
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def save_jpeg(png: bytes, path: Path, quality: int) -> None:
    with Image.open(BytesIO(png)) as image:
        image.convert("RGB").save(path, "JPEG", quality=quality, optimize=True)
