"""
enrich_claude.py — Step 5: Deep enrichment via Claude with motion frame sequence.

This is the core taste extraction step. Unlike the original plan:
  1. We pass the HERO screenshot + up to 5 SEQUENTIAL FRAMES to Claude
  2. We include extracted GSAP/CSS code so Claude sees the real motion code
  3. We ask for motion language SEPARATELY from visual analysis
  4. Output includes a structured motion vocabulary entry

Cost estimate: ~$0.08–0.12 per site (images + text)
"""
import json
import base64
import time
from pathlib import Path
from rich.console import Console
from litellm import completion
from config import DATA_DIR, VISION_MODEL, REASONING_MODEL, LOGS_DIR

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


def build_motion_context(site_id: str) -> str:
    """Build a text summary of extracted motion code for the prompt."""
    motion_path = DATA_DIR / site_id / "motion_code.json"
    if not motion_path.exists():
        return "No motion code extracted."

    m = json.loads(motion_path.read_text())
    libs = m.get("libraries_detected", {})
    active_libs = [k for k, v in libs.items() if v]

    parts = []
    if active_libs:
        parts.append(f"Motion libraries detected: {', '.join(active_libs)}")

    gsap_calls = m.get("gsap_calls", [])
    if gsap_calls:
        parts.append(f"\nGSAP calls intercepted ({len(gsap_calls)} total, first 3 shown):")
        for call in gsap_calls[:3]:
            parts.append(f"  gsap.{call.get('method','?')}({call.get('args','?')[:200]})")

    keyframes = m.get("css_keyframes", [])
    if keyframes:
        parts.append(f"\nCSS @keyframes ({len(keyframes)} found, first 2 shown):")
        for kf in keyframes[:2]:
            parts.append(f"  {kf[:300]}")

    transitions = m.get("css_transitions", [])
    if transitions:
        parts.append(f"\nCSS transitions ({len(transitions)} rules):")
        for t in transitions[:3]:
            parts.append(f"  {t.get('selector','?')}: {t.get('transition','?')[:100]}")

    scroll_data = m.get("scroll_patterns", {})
    if scroll_data.get("data_aos", 0) > 0:
        parts.append(f"\nAOS (Animate On Scroll) elements: {scroll_data['data_aos']}")
    if scroll_data.get("locomotive"):
        parts.append("Locomotive Scroll detected (smooth scroll library)")

    return "\n".join(parts) if parts else "No significant motion code found."


def enrich_with_claude(site_id: str, entry: dict) -> dict | None:
    """
    Send hero screenshot + motion frames + code context to Claude.
    Returns structured enrichment dict.
    """
    site_dir   = DATA_DIR / site_id
    hero_path  = site_dir / "screenshot_hero.png"

    if not hero_path.exists():
        console.print(f"[yellow]⚠ No screenshot for {site_id}[/yellow]")
        return None

    # ── Build image content blocks ─────────────────────────────────────────
    content_blocks = []

    # 1. Hero screenshot
    hero_b64, hero_type = load_image_b64(hero_path, max_kb=1500)
    content_blocks.append({
        "type": "image_url",
        "image_url": {"url": f"data:{hero_type};base64,{hero_b64}"}
    })
    content_blocks.append({
        "type": "text",
        "text": "↑ Above: Above-the-fold hero screenshot (static state)\n",
    })

    # ── Context from previous analysis steps (Stage 1) ───────────────
    metadata        = entry.get("metadata") or {}
    visual_context  = json.dumps(entry.get("visual", {}), indent=2)
    motion_context  = build_motion_context(site_id)
    dom_computed    = json.dumps(metadata.get("dom_structure", {}).get("computed_styles", []), indent=2)

    # ── Stage 2: Forensic VLM Prompt ──────────────────────────────────
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
        console.print(f"  [dim]↳ Running Stage 2: {VISION_MODEL} (Forensic VLM)...[/dim]")
        vision_response = completion(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": content_blocks}],
            max_tokens=1000,
            num_ctx=4096
        )
        
        vlm_json_str = vision_response.choices[0].message.content.strip()
        
        # Clean markdown fences from VLM output just in case
        if "```json" in vlm_json_str:
            vlm_json_str = vlm_json_str.split("```json")[1].split("```")[0]
        elif vlm_json_str.startswith("```"):
            vlm_json_str = vlm_json_str.split("```")[1]
            
        (site_dir / "stage2_vlm_raw.json").write_text(vlm_json_str)

        # ── Stage 3: Taste Synthesizer (Gemma) ─────────────────────────
        synthesizer_prompt = f"""You are analyzing verified structural data from a top-tier Awwwards website.

METRIC SHEET (Stage 1 Deterministic Math):
DOM Computed Styles: {dom_computed[:3000]}
Motion Context: {motion_context}
Visual Context (K-Means): {visual_context}

VISUAL SCHEMA (Stage 2 Forensic VLM):
{vlm_json_str}

TASK:
Analyze the structural tension between the typographic grid (from the DOM styles) and the organic elements (from the Visual Schema).
Derive the exact design rule this site uses to achieve visual prestige without using filler adjectives.
Contrast the observed styles against a standard Bootstrap 5 default implementation to provide a negative baseline.

Respond ONLY with a valid JSON object matching this exact schema:
{{
  "design_rationale": ["paragraph 1", "paragraph 2"],
  "taste_rule": "The core design law this site exploits",
  "negative_baseline_contrast": "How this differs from generic Bootstrap 5 defaults",
  "motion_language": "Physical description of the GSAP / Scroll logic",
  "premium_signals": ["signal 1", "signal 2"],
  "style_tags": ["tag1", "tag2"]
}}"""

        console.print(f"  [dim]↳ Running Stage 3: {REASONING_MODEL} (Taste Synthesizer)...[/dim]")
        extraction_response = completion(
            model=REASONING_MODEL,
            messages=[{"role": "user", "content": synthesizer_prompt}],
            max_tokens=2500
        )
        
        json_raw = extraction_response.choices[0].message.content.strip()
        
        # Clean markdown fences from gemma output just in case
        if "```json" in json_raw:
            json_raw = json_raw.split("```json")[1].split("```")[0]
        elif json_raw.startswith("```"):
            json_raw = json_raw[3:].split("```")[0]

        result = json.loads(json_raw.strip())
        result["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        result["model"]       = f"{VISION_MODEL} (Vision) -> {REASONING_MODEL} (Struct)"

        (site_dir / "taste_rationale.json").write_text(json.dumps(result, indent=2))
        
        # Cleanup the raw md file on success
        # try:
        #     (site_dir / "claude_rationale_raw.md").unlink()
        # except FileNotFoundError:
        #     pass
            
        console.print(f"[green]✓[/green] {site_id}: enriched perfectly with Two-Step Pipeline")
        return result

    except json.JSONDecodeError as e:
        console.print(f"[red]✗ JSON parse error for {site_id} from {REASONING_MODEL}: {e}[/red]")
        raw_save = {"raw_response": json_raw, "parse_error": True}
        (site_dir / "claude_rationale_raw.json").write_text(json.dumps(raw_save, indent=2))
        return None
    except Exception as e:
        console.print(f"[red]✗ Enrichment failed for {site_id}: {e}[/red]")
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Enrich a single site ID")
    args = parser.parse_args()

    if not VISION_MODEL:
        console.print("[red]✗ VISION_MODEL not set in config.py[/red]")
        exit(1)

    # Load master dataset
    from compile import load_master
    entries = load_master()

    targets = [args.site] if args.site else list(entries.keys())

    for sid in targets:
        if sid not in entries:
            console.print(f"[yellow]⚠ {sid} not in master dataset — run compile.py first[/yellow]")
            continue
        if entries[sid].get("design_rationale") is not None:
            console.print(f"[yellow]⏭ Skip[/yellow] {sid}")
            continue

        result = enrich_with_claude(sid, entries[sid])
        if result:
            entries[sid]["design_rationale"] = result
            # Update master
            from compile import save_master
            save_master(entries)

        time.sleep(2)  # rate limit buffer
