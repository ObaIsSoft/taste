"""
analyzer.py — Step 3: Extract visual DNA from screenshots.
"""
import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageStat, ImageChops
from colorthief import ColorThief
from rich.console import Console
from config import DATA_DIR

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
        return "dark-luxury" if avg_saturation < 0.3 else "dark-vibrant"
    elif avg_brightness > 0.85:
        return "minimal-white" if avg_saturation < 0.2 else "bright-playful"
    elif avg_saturation > 0.6:
        return "bold-colorful"
    elif avg_saturation < 0.15:
        return "monochromatic"
    else:
        return "balanced-mid"


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


def calculate_asymmetry(img: Image.Image) -> float:
    """
    Calculate visual center of mass on the X-axis based on luminance.
    Returns a score 0-1. 0 = perfectly centered, 1 = extremely skewed left/right.
    """
    img_gray = img.convert("L")
    w, h = img_gray.size
    
    # Calculate moments
    total_mass = 0
    m_x = 0
    pixels = img_gray.load()
    
    # Fast sampling every 10th pixel
    for x in range(0, w, 10):
        for y in range(0, h, 10):
            # Invert so dark pixels have 'mass' on a light background, or vice versa?
            # Let's just use raw variance from center
            val = pixels[x, y]
            total_mass += val
            m_x += val * x
            
    if total_mass == 0:
        return 0
        
    center_of_mass_x = m_x / total_mass
    # Distance from true center (w/2) normalized by half-width
    true_center = w / 2
    distance = abs(center_of_mass_x - true_center)
    asymmetry_score = distance / true_center
    
    return round(asymmetry_score, 3)


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
    
    total_var = (r_var + g_var + b_var) / (255**2 * 3) # normalize roughly to 0-1
    return round(total_var * 10, 3) # Scale up for readability


def analyze_image(site_id: str) -> dict | None:
    """Run full visual analysis on a site's hero screenshot."""
    site_dir  = DATA_DIR / site_id
    img_path  = site_dir / "screenshot_hero.png"
    full_path = site_dir / "screenshot_full.png"

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
        "asymmetry_score":   calculate_asymmetry(img),
        "color_variance":    calculate_color_variance(palette),
        "file_size_kb":      round(img_path.stat().st_size / 1024, 1),
    }

    (site_dir / "visual_analysis.json").write_text(json.dumps(analysis, indent=2))
    console.print(
        f"[green]✓[/green] {site_id}: "
        f"palette=[bold]{analysis['palette_mood']}[/bold], "
        f"brightness={analysis['avg_brightness']}, "
        f"whitespace={analysis['whitespace_ratio']}"
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
            if (site_dir / "visual_analysis.json").exists():
                console.print(f"[yellow]⏭ Skip[/yellow] {site_dir.name}")
                continue
            analyze_image(site_dir.name)
