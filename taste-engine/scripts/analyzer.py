"""
analyzer.py — Step 3: Extract visual DNA from screenshots + DOM metadata.

V2 changes:
  - Replaced broken luminance asymmetry with DOM-based layout imbalance
  - Added 3x3 quadrant distribution (spatial signature)
  - Added DOM features: font variance, letter-spacing range, z-index depth, section count
  - Reads metadata.json for DOM-derived features
"""
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageStat, ImageChops
from colorthief import ColorThief
from rich.console import Console
from config import DATA_DIR, VISUAL_FILE, METADATA_FILE

console = Console()


def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def color_brightness(rgb: tuple) -> float:
    """Perceived brightness 0–1 (human eye weighting)."""
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def color_saturation(rgb: tuple) -> float:
    """Simple saturation 0–1."""
    r, g, b = [x / 255 for x in rgb]
    cmax, cmin = max(r, g, b), min(r, g, b)
    return (cmax - cmin) / cmax if cmax > 0 else 0


def classify_palette(colors: list[tuple]) -> str:
    """Rough palette mood from dominant colors."""
    brightness_vals = [color_brightness(c) for c in colors]
    saturation_vals = [color_saturation(c) for c in colors]
    avg_brightness  = sum(brightness_vals) / len(brightness_vals)
    avg_saturation  = sum(saturation_vals) / len(saturation_vals)

    if avg_brightness < 0.2:
        return "dark-desaturated" if avg_saturation < 0.3 else "dark-highly-saturated"
    elif avg_brightness > 0.85:
        return "bright-desaturated" if avg_saturation < 0.2 else "bright-highly-saturated"
    elif avg_saturation > 0.6:
        return "mid-brightness-highly-saturated"
    elif avg_saturation < 0.15:
        return "monochromatic-neutral"
    else:
        return "balanced-midtones"


def estimate_whitespace_ratio(img: Image.Image) -> float:
    """
    Estimate whitespace by counting near-white + near-black pixels.
    High ratio = lots of breathing room (minimal design).
    """
    img_rgb = img.convert("RGB").resize((200, 200))  # fast downsample
    pixels  = list(img_rgb.getdata())
    extreme = sum(
        1 for r, g, b in pixels
        if (r > 230 and g > 230 and b > 230) or (r < 30 and g < 30 and b < 30)
    )
    return round(extreme / len(pixels), 3)


def calculate_color_variance(colors: list[tuple]) -> float:
    """
    Calculate how 'rhythmic' or distinct the palette is.
    High variance = high rhythm/contrast. Low variance = monochromatic block.
    """
    if not colors:
        return 0.0
    r_vals = [c[0] for c in colors]
    g_vals = [c[1] for c in colors]
    b_vals = [c[2] for c in colors]

    r_var = sum((x - sum(r_vals)/len(r_vals))**2 for x in r_vals) / len(r_vals)
    g_var = sum((x - sum(g_vals)/len(g_vals))**2 for x in g_vals) / len(g_vals)
    b_var = sum((x - sum(b_vals)/len(b_vals))**2 for x in b_vals) / len(b_vals)

    total_var = (r_var + g_var + b_var) / (255**2 * 3)  # normalize roughly to 0-1
    return round(total_var * 10, 3)  # Scale up for readability


# ── V2: DOM-based metrics (from metadata.json) ─────────────────────────────


def dom_layout_imbalance(computed_styles: list[dict], viewport_w: int = 1440) -> float:
    """
    Layout imbalance: how unevenly is element area distributed
    across the vertical midline, weighted by element area.
    0.0 = perfectly balanced, 1.0 = completely one-sided.

    This replaces the broken luminance-center-of-mass asymmetry,
    which had no variance across all 100 sites (all scored 0.001-0.25).
    """
    center = viewport_w / 2
    left_mass = 0.0
    right_mass = 0.0

    for el in computed_styles:
        bbox = el.get("bbox", {})
        x = bbox.get("x", 0)
        w = bbox.get("w", 0)
        h = bbox.get("h", 0)
        if w == 0 or h == 0:
            continue
        el_center = x + w / 2
        area = w * h
        if el_center < center:
            left_mass += area
        else:
            right_mass += area

    total = left_mass + right_mass
    if total == 0:
        return 0.0
    return round(abs(left_mass - right_mass) / total, 3)


def dom_quadrant_distribution(computed_styles: list[dict], viewport_w: int = 1440, viewport_h: int = 900) -> list[float]:
    """
    3x3 quadrant distribution: what fraction of element area falls in each
    grid cell. Captures spatial signature: "top-left heavy" vs "centered"
    vs "diagonal" — the actual vocabulary of layout.

    Returns 9 floats (0-1) summing to ~1.0, ordered left-to-right, top-to-bottom.
    """
    # Define quadrant boundaries
    x_edges = [0, viewport_w / 3, 2 * viewport_w / 3, viewport_w]
    y_edges = [0, viewport_h / 3, 2 * viewport_h / 3, viewport_h]

    quadrant_mass = [0.0] * 9

    for el in computed_styles:
        bbox = el.get("bbox", {})
        x = bbox.get("x", 0)
        y = bbox.get("y", 0)
        w = bbox.get("w", 0)
        h = bbox.get("h", 0)
        if w == 0 or h == 0:
            continue

        el_center_x = x + w / 2
        el_center_y = y + h / 2
        area = w * h

        # Find which quadrant this element belongs to
        qx = min(2, max(0, int(el_center_x / (viewport_w / 3))))
        qy = min(2, max(0, int(el_center_y / (viewport_h / 3))))
        quadrant_mass[qy * 3 + qx] += area

    total = sum(quadrant_mass)
    if total == 0:
        return [0.0] * 9
    return [round(m / total, 3) for m in quadrant_mass]


def dom_typography_features(computed_styles: list[dict]) -> dict:
    """
    Extract typography features from DOM computed styles.
    - font_size_variance: how much do font sizes vary? (flat vs hierarchical)
    - letter_spacing_range: min/max letter-spacing (micro-typography)
    - z_index_depth: how many layers of z-index? (depth/complexity)
    - section_count: how many sections? (page structure)
    """
    font_sizes = []
    letter_spacings = []
    z_indices = set()
    section_count = 0

    for el in computed_styles:
        # Font sizes
        fs_str = el.get("fontSize", "0px")
        try:
            fs = float(fs_str.replace("px", ""))
            if fs > 0:
                font_sizes.append(fs)
        except (ValueError, AttributeError):
            pass

        # Letter spacing
        ls_str = el.get("letterSpacing", "normal")
        if ls_str != "normal":
            try:
                ls = float(ls_str.replace("px", ""))
                letter_spacings.append(ls)
            except (ValueError, AttributeError):
                pass

        # Z-index
        z_str = el.get("zIndex", "auto")
        if z_str != "auto":
            try:
                z_indices.add(int(z_str))
            except (ValueError, TypeError):
                pass

        # Section count
        if el.get("tag") == "SECTION":
            section_count += 1

    # Font size variance (coefficient of variation)
    if len(font_sizes) >= 2:
        mean_fs = sum(font_sizes) / len(font_sizes)
        variance = sum((fs - mean_fs) ** 2 for fs in font_sizes) / len(font_sizes)
        std_fs = variance ** 0.5
        font_size_cv = round(std_fs / mean_fs, 3) if mean_fs > 0 else 0.0
    else:
        font_size_cv = 0.0

    # Letter spacing range
    if letter_spacings:
        ls_range = round(max(letter_spacings) - min(letter_spacings), 1)
        ls_min = round(min(letter_spacings), 1)
        ls_max = round(max(letter_spacings), 1)
    else:
        ls_range = 0.0
        ls_min = 0.0
        ls_max = 0.0

    return {
        "font_size_cv": font_size_cv,          # coefficient of variation
        "font_size_min": round(min(font_sizes), 1) if font_sizes else 0,
        "font_size_max": round(max(font_sizes), 1) if font_sizes else 0,
        "letter_spacing_range": ls_range,
        "letter_spacing_min": ls_min,
        "letter_spacing_max": ls_max,
        "z_index_depth": len(z_indices),
        "section_count": section_count,
    }


def analyze_image(site_id: str) -> dict | None:
    """Run full visual analysis on a site's hero screenshot + DOM metadata."""
    site_dir  = DATA_DIR / site_id
    img_path  = site_dir / "screenshot_hero.png"
    full_path = site_dir / "screenshot_full.png"
    meta_path = site_dir / METADATA_FILE

    if not img_path.exists():
        console.print(f"[yellow]⚠ No hero screenshot for[/yellow] {site_id}")
        return None

    img = Image.open(img_path)
    w, h = img.size

    # ── Color extraction ───────────────────────────────────────────────────
    ct = ColorThief(str(img_path))
    try:
        dominant = ct.get_color(quality=1)
        palette  = ct.get_palette(color_count=6, quality=1)
    except Exception:
        dominant = (128, 128, 128)
        palette  = [(128, 128, 128)]

    # ── Image stats ────────────────────────────────────────────────────────
    stat        = ImageStat.Stat(img.convert("RGB"))
    avg_rgb     = tuple(int(v) for v in stat.mean[:3])
    brightness  = color_brightness(avg_rgb)

    # ── Full-page height ratio ─────────────────────────────────────────────
    full_height = None
    if full_path.exists():
        full_img    = Image.open(full_path)
        full_height = full_img.height

    # ── V2: DOM-based metrics ──────────────────────────────────────────────
    computed_styles = []
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            computed_styles = meta.get("dom_structure", {}).get("computed_styles", [])
        except Exception:
            pass

    # DOM-based layout imbalance (replaces broken luminance asymmetry)
    layout_imbalance = dom_layout_imbalance(computed_styles, viewport_w=w)

    # 3x3 quadrant distribution
    quadrant_dist = dom_quadrant_distribution(computed_styles, viewport_w=w, viewport_h=h)

    # Typography + structure features
    typo_features = dom_typography_features(computed_styles)

    analysis = {
        "dimensions": {"width": w, "height": h},
        "full_page_height_px": full_height,
        "scroll_depth_multiplier": round(full_height / h, 1) if full_height else None,
        "dominant_color": {
            "rgb": dominant,
            "hex": rgb_to_hex(dominant),
            "brightness": round(color_brightness(dominant), 3),
            "saturation": round(color_saturation(dominant), 3),
        },
        "palette": [
            {
                "rgb": c,
                "hex": rgb_to_hex(c),
                "brightness": round(color_brightness(c), 3),
                "saturation": round(color_saturation(c), 3),
            }
            for c in palette
        ],
        "palette_mood":      classify_palette(palette),
        "avg_brightness":    round(brightness, 3),
        "whitespace_ratio":  estimate_whitespace_ratio(img),
        "color_variance":    calculate_color_variance(palette),
        "file_size_kb":      round(img_path.stat().st_size / 1024, 1),

        # ── V2: DOM-based metrics ─────────────────────────────────────────
        "layout_imbalance":         layout_imbalance,
        "quadrant_distribution":    quadrant_dist,
        "font_size_cv":             typo_features["font_size_cv"],
        "font_size_min":            typo_features["font_size_min"],
        "font_size_max":            typo_features["font_size_max"],
        "letter_spacing_range":    typo_features["letter_spacing_range"],
        "letter_spacing_min":       typo_features["letter_spacing_min"],
        "letter_spacing_max":       typo_features["letter_spacing_max"],
        "z_index_depth":            typo_features["z_index_depth"],
        "section_count":            typo_features["section_count"],
        "dom_element_count":        len(computed_styles),
    }

    (site_dir / VISUAL_FILE).write_text(json.dumps(analysis, indent=2))
    console.print(
        f"[green]✓[/green] {site_id}: "
        f"palette=[bold]{analysis['palette_mood']}[/bold], "
        f"brightness={analysis['avg_brightness']}, "
        f"whitespace={analysis['whitespace_ratio']}, "
        f"imbalance={analysis['layout_imbalance']}"
    )
    return analysis


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Analyze a single site ID")
    args = parser.parse_args()

    if args.site:
        analyze_image(args.site)
    else:
        for site_dir in sorted(DATA_DIR.iterdir()):
            if not site_dir.is_dir() or not (site_dir / "screenshot_hero.png").exists():
                continue
            # Force re-analysis to capture new metrics (removed the skip check)
            analyze_image(site_dir.name)
