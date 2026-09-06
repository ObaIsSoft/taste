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
import anthropic
from config import DATA_DIR, CLAUDE_MODEL, ANTHROPIC_API_KEY, LOGS_DIR

console = Console()
client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


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
        "type": "image",
        "source": {"type": "base64", "media_type": hero_type, "data": hero_b64},
    })
    content_blocks.append({
        "type": "text",
        "text": "↑ Above: Above-the-fold hero screenshot (static state)\n",
    })

    # 2. Sequential motion frames (if available)
    manifest_path = site_dir / "frames_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        frames   = manifest.get("frames", [])[:4]  # max 4 frames (API limit)
        timestamps = manifest.get("timestamps", [])

        if frames:
            content_blocks.append({
                "type": "text",
                "text": (
                    f"\n↓ Below: {len(frames)} sequential frames from the site's "
                    "interaction recording (scroll + hover journey).\n"
                    "These show how the site MOVES over time, not just its static state.\n"
                ),
            })
            for i, (frame_path, ts) in enumerate(zip(frames, timestamps)):
                try:
                    frame_b64, frame_type = load_image_b64(frame_path, max_kb=800)
                    content_blocks.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": frame_type, "data": frame_b64},
                    })
                    content_blocks.append({
                        "type": "text",
                        "text": f"↑ Frame {i+1} at t={ts}s into the interaction\n",
                    })
                except Exception:
                    pass

    # ── Context from previous analysis steps ──────────────────────────────
    llava_context   = json.dumps(entry.get("llava", {}), indent=2)
    visual_context  = json.dumps(entry.get("visual", {}), indent=2)
    motion_context  = build_motion_context(site_id)
    metadata        = entry.get("metadata", {})

    # ── Prompt ────────────────────────────────────────────────────────────
    prompt = f"""You are the creative director at a tier-1 digital agency. You are building a design taste database.

SITE: {metadata.get('title', 'Unknown')} ({metadata.get('url', '')})

PREVIOUS ANALYSIS (from local AI model):
{llava_context}

VISUAL DNA (extracted programmatically):
{visual_context}

MOTION CODE (extracted from live JavaScript/CSS):
{motion_context}

You have been given the hero screenshot AND a sequence of frames from a recorded scroll interaction.
Use ALL of this data together to write a complete taste profile.

Respond ONLY with a valid JSON object:
{{
  "design_rationale": "3-4 paragraphs. Explain WHY this design works: grid logic, visual hierarchy, whitespace intention, typographic system, brand positioning. Be specific. Reference what you actually see.",
  
  "motion_language": {{
    "personality": ["3 words, e.g. 'cinematic', 'breathing', 'precise'"],
    "easing_type": "spring-physics | ease-out-cubic | linear | bounce | custom-bezier",
    "pacing": "fast-snappy | medium-confident | slow-cinematic | varied-editorial",
    "entrance_pattern": "what enters first vs last? e.g. 'background-first, then headline-stagger, then CTA-fade'",
    "scroll_behavior": "none | subtle-parallax | section-reveals | scroll-scrub | full-scroll-narrative",
    "hover_quality": "none | color-shift | scale-bounce | underline-draw | cursor-morph | complex",
    "techniques_identified": ["list of specific techniques you can infer from the frames + code"]
  }},
  
  "gsap_spec": {{
    "description": "If GSAP is present, describe the timeline logic you'd write to recreate this",
    "example_timeline": "gsap.timeline code snippet that approximates what you see, or null if not applicable"
  }},
  
  "design_tokens": {{
    "primary_color":    "#hex",
    "secondary_color":  "#hex",
    "background_color": "#hex",
    "text_color":       "#hex",
    "font_heading":     "Font name or 'Unknown'",
    "font_body":        "Font name or 'Unknown'",
    "spacing_unit":     "4px | 8px | 10px | 16px",
    "border_radius":    "none | subtle (4-8px) | medium (12-16px) | rounded (20px+) | pill",
    "shadow_style":     "none | soft | hard | glow | colored"
  }},
  
  "premium_signals": ["specific observable details that elevate this above generic, e.g. 'custom variable font with weight animation', 'grain texture overlay at 0.04 opacity'"],
  
  "what_makes_it_fail": "Honest critique — what would make this design feel generic or fail? Be specific.",
  
  "style_tags": ["5-10 short searchable tags, e.g. 'editorial', 'dark', 'motion-heavy', 'luxury', 'webgl'"]
}}"""

    content_blocks.append({"type": "text", "text": prompt})

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{"role": "user", "content": content_blocks}],
        )

        raw = message.content[0].text.strip()

        # Strip markdown fences
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif raw.startswith("```"):
            raw = raw[3:].split("```")[0]

        result = json.loads(raw.strip())
        result["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        result["model"]       = CLAUDE_MODEL

        (site_dir / "claude_rationale.json").write_text(json.dumps(result, indent=2))
        console.print(f"[green]✓[/green] {site_id}: enriched with motion + taste analysis")
        return result

    except json.JSONDecodeError as e:
        console.print(f"[red]✗ JSON parse error for {site_id}: {e}[/red]")
        raw_save = {"raw_response": raw, "parse_error": True}
        (site_dir / "claude_rationale_raw.json").write_text(json.dumps(raw_save, indent=2))
        return None
    except Exception as e:
        console.print(f"[red]✗ Claude failed for {site_id}: {e}[/red]")
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Enrich a single site ID")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        console.print("[red]✗ ANTHROPIC_API_KEY not set. Create a .env file from .env.example[/red]")
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
