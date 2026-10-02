"""Layout and type features from the DOM boxes captured at scroll 0.

Only content boxes count (text, media, controls), clipped to the hero viewport:
wrappers such as sections and main would otherwise fill every measure with
the page's own frame. Boxes centred on the midline count half on each side.
Missing inputs give None, never zero.
"""

from __future__ import annotations

import statistics
from typing import Any

from taste_engine.settings import AnalysisSettings

_MEDIA_TAGS = frozenset({"img", "video", "canvas", "svg"})
_CONTENT_TAGS = _MEDIA_TAGS | {"button", "input"}


def _clip(box: dict[str, Any], width: float, height: float) -> tuple[float, float, float]:
    x0, y0 = max(box["x"], 0), max(box["y"], 0)
    x1, y1 = min(box["x"] + box["w"], width), min(box["y"] + box["h"], height)
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return area, (x0 + x1) / 2, (y0 + y1) / 2


def _rounded(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def layout_features(
    dom: dict[str, Any], tokens: dict[str, Any], cfg: AnalysisSettings
) -> dict[str, object]:
    width, height = dom["viewport"]["width"], dom["viewport"]["height"]
    left = right = media_area = 0.0
    text_grid = [0.0] * 9
    sizes: list[float] = []
    for box in dom["elements"]:
        is_text = bool(box.get("text_length"))
        if not is_text and box.get("tag") not in _CONTENT_TAGS:
            continue
        area, cx, cy = _clip(box, width, height)
        if area <= 0:
            continue
        offset = cx - width / 2
        if abs(offset) <= cfg.midline_tie_px:
            left += area / 2
            right += area / 2
        elif offset < 0:
            left += area
        else:
            right += area
        if is_text:
            column = min(2, int(cx / (width / 3)))
            row = min(2, int(cy / (height / 3)))
            text_grid[row * 3 + column] += area
            sizes.append(box["font_size"])
        elif box.get("tag") in _MEDIA_TAGS:
            media_area += area

    total = left + right
    grid_total = sum(text_grid)
    spacing = tokens.get("spacing", [])
    spacing_count = sum(item["count"] for item in spacing)
    regular = sum(item["count"] for item in spacing if item["px"] % cfg.spacing_unit_px == 0)
    median_size = statistics.median(sizes) if sizes else None

    return {
        "page_height_screens": _rounded(dom["page_height"] / height, 2),
        "hero_text_boxes": len(sizes),
        "layout_imbalance": _rounded(abs(left - right) / total) if total else None,
        "text_quadrants": [round(c / grid_total, 4) for c in text_grid] if grid_total else None,
        "media_coverage": _rounded(min(1.0, media_area / (width * height))),
        "display_ratio": _rounded(max(sizes) / median_size, 2) if median_size else None,
        "font_size_cv": _rounded(statistics.pstdev(sizes) / statistics.fmean(sizes))
        if len(sizes) > 1
        else None,
        "font_families": len(tokens.get("fonts", [])),
        "font_sizes": len(tokens.get("font_sizes", [])),
        "text_colours": len(tokens.get("text_colors", [])),
        "spacing_regularity": _rounded(regular / spacing_count) if spacing_count else None,
        "corner_radii": len(tokens.get("radii", [])),
        "shadows": tokens.get("shadows"),
    }
