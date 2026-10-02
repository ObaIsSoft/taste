"""Pixel features of a still.

Whitespace is measured against the page's own background colour (the most
common colour along the border), so a dark minimal page and a light one are
treated alike, and black text is not mistaken for empty space.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from taste_engine.settings import AnalysisSettings


def _load(path: Path, width: int) -> Image.Image:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
    height = max(1, round(rgb.height * width / rgb.width))
    return rgb.resize((width, height))


def _background(pixels: np.ndarray, quant: int) -> np.ndarray:
    border = np.concatenate([pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]])
    bins, counts = np.unique((border // quant).astype(int), axis=0, return_counts=True)
    return bins[counts.argmax()] * quant + quant / 2


def _palette(image: Image.Image, size: int) -> list[dict[str, float | str]]:
    quantised = image.quantize(colors=size, method=Image.Quantize.MEDIANCUT)
    colours = quantised.getpalette() or []
    total = image.width * image.height
    entries = []
    for count, index in sorted(quantised.getcolors() or [], reverse=True):
        r, g, b = colours[index * 3 : index * 3 + 3]
        entries.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "share": round(count / total, 4)})
    return entries


def pixel_features(path: Path, cfg: AnalysisSettings) -> dict[str, object]:
    image = _load(path, cfg.thumb_width)
    pixels = np.asarray(image, dtype=np.float32)
    background = _background(pixels, cfg.background_quant)
    distance = np.linalg.norm(pixels - background, axis=2)

    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    rg, yb = r - g, 0.5 * (r + g) - b  # Hasler and Suesstrunk opponent channels
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    steps = np.abs(np.diff(luminance, axis=1))[:-1, :] + np.abs(np.diff(luminance, axis=0))[:, :-1]

    return {
        "background_hex": "#{:02x}{:02x}{:02x}".format(*(int(c) for c in background)),
        "background_luminance": round(
            float(0.2126 * background[0] + 0.7152 * background[1] + 0.0722 * background[2]) / 255, 4
        ),
        "whitespace_ratio": round(float((distance <= cfg.background_tolerance).mean()), 4),
        "colourfulness": round(
            float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())), 2
        ),
        "luminance_mean": round(float(luminance.mean()) / 255, 4),
        "luminance_contrast": round(float(luminance.std()) / 255, 4),
        "edge_density": round(float((steps > cfg.edge_threshold).mean()), 4),
        "palette": _palette(image, cfg.palette_size),
    }
