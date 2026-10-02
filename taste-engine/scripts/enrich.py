"""
enrich.py — V2: VLM feature extraction (not label generation).
Writes stage2_vlm_raw.json (forensic features). See config.VLM_RAW_FILE.

V2 changes:
  - VLM is a FEATURE EXTRACTOR, not a label generator
  - No taste_rationale.json generation (replaced by voter reasoning)
  - No gemma4 synthesizer step (no longer needed)
  - VLM analyzes hero screenshot only (no keyframes)
"""
import json
import base64
import time
from pathlib import Path
from rich.console import Console
from litellm import completion
from config import DATA_DIR, VISION_MODEL, VLM_RAW_FILE, MOTION_CODE_FILE

console = Console()


def load_image_b64(path: str | Path, max_kb: int = 2000) -> tuple[str, str]:
    """
    Load image as base64. If over max_kb, downsample.
    Returns (base64_string, media_type).
    """
    from PIL import Image
    import io

    path = Path(path)
    img  = Image.open(path).convert("RGB")

    # Resize if too large (keep aspect ratio)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    if buf.tell() > max_kb * 1024:
        ratio = (max_kb * 1024 / buf.tell()) ** 0.5
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        img   = img.resize((new_w, new_h), Image.LANCZOS)
        buf   = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)

    return base64.b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"


def extract_vlm_features(site_id: str) -> dict | None:
    """
    V2: VLM as feature extractor (not label generator).
    Analyzes the hero screenshot and outputs structured forensic features.
    These features are INPUT CONTEXT for the DPO prompt, not labels.
    """
    site_dir = DATA_DIR / site_id
    hero_path = site_dir / "screenshot_hero.png"

    if not hero_path.exists():
        console.print(f"[yellow]⚠ No screenshot for {site_id}[/yellow]")
        return None

    hero_b64, hero_type = load_image_b64(hero_path, max_kb=600)

    vlm_prompt = """Analyze the image. Output a factual JSON object describing the physical elements present.
DO NOT use subjective words like 'clean', 'modern', 'premium', or 'engaging'. State ONLY observable facts.

Use this exact JSON schema:
{
  "focal_subject": {
    "type": "human_face | 3d_render | product_mockup | pure_typography | abstract_graphic | none",
    "description": "Short factual description of the main focal element"
  },
  "background_style": {
    "type": "flat_color | gradient | textured | video_still | photographic",
    "dominant_hue": "descriptive name",
    "has_grain_or_noise": false
  },
  "badges_and_overlays": [
    "List any award ribbons, floating badges, floating tags, or sticky navbars visible"
  ],
  "whitespace_distribution": "dense | balanced | extreme_empty_space"
}
"""

    content_blocks = [
        {"type": "image_url", "image_url": {"url": f"data:{hero_type};base64,{hero_b64}"}},
        {"type": "text", "text": vlm_prompt}
    ]

    try:
        console.print(f"  [dim]↳ Running VLM feature extraction: {VISION_MODEL}...[/dim]")
        vision_response = completion(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": content_blocks}],
            max_tokens=1000,
            num_ctx=4096
        )

        vlm_json_str = vision_response.choices[0].message.content.strip()

        # Clean markdown fences
        if "```json" in vlm_json_str:
            vlm_json_str = vlm_json_str.split("```json")[1].split("```")[0]
        elif vlm_json_str.startswith("```"):
            vlm_json_str = vlm_json_str.split("```")[1]

        vlm_data = json.loads(vlm_json_str.strip())
        vlm_data["extracted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        vlm_data["model"] = VISION_MODEL

        (site_dir / VLM_RAW_FILE).write_text(json.dumps(vlm_data, indent=2))
        console.print(f"[green]✓[/green] {site_id}: VLM features extracted")
        return vlm_data

    except json.JSONDecodeError as e:
        console.print(f"[red]✗ JSON parse error for {site_id}: {e}[/red]")
        raw_save = {"raw_response": vlm_json_str, "parse_error": True}
        (site_dir / VLM_RAW_FILE).write_text(json.dumps(raw_save, indent=2))
        return None
    except Exception as e:
        console.print(f"[red]✗ VLM extraction failed for {site_id}: {e}[/red]")
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Extract VLM features for a single site ID")
    args = parser.parse_args()

    if not VISION_MODEL:
        console.print("[red]✗ VLM_MODEL not set in config.py[/red]")
        exit(1)

    targets = [args.site] if args.site else [
        d.name for d in sorted(DATA_DIR.iterdir())
        if d.is_dir() and (d / "screenshot_hero.png").exists()
    ]

    for sid in targets:
        if (DATA_DIR / sid / VLM_RAW_FILE).exists():
            console.print(f"[yellow]⏭ Skip[/yellow] {sid}")
            continue
        extract_vlm_features(sid)
        time.sleep(1)
