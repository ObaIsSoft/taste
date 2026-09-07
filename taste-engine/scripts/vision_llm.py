"""
vision_llm.py — Step 4: Local LLaVA pass on hero screenshot.
"""
import sys
import json
import base64
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from config import DATA_DIR, OLLAMA_URL, OLLAMA_MODEL

console = Console()

DESIGN_PROMPT = """You are analyzing a premium website screenshot as a senior UI designer.
Respond ONLY with a valid JSON object — no markdown, no explanations.

{
  "layout_type": "Describe the exact layout structure (e.g., 'centered-hero', 'asymmetric', 'radial-focus', or any novel layout observed)",
  "typography_style": "Describe the typographic system and pairing (e.g., 'high-contrast-editorial', 'neo-brutalist-mono', etc.)",
  "color_mood": "Describe the emotional mood of the color palette (e.g., 'dark-luxury', 'clinical-minimal', 'acid-neon', etc.)",
  "motion_impression": "Describe the static impression of motion/depth (e.g., 'heavy-webgl', 'scroll-driven-story', etc.)",
  "design_era": "Estimate the design era or paradigm (e.g., '2020-glassmorphism', 'post-2025-spatial', etc.)",
  "aesthetic_category": "Describe the aesthetic genre (e.g., 'luxury-ecommerce', 'indie-portfolio', 'fintech-corporate', etc.)",
  "whitespace_use": "Describe how whitespace is utilized (e.g., 'ultra-generous', 'claustrophobic-brutalist', 'balanced', etc.)",
  "notable_elements": ["array of specific unique elements you can see, e.g. oversized-type, grain-texture, custom-cursor, 3d-object, video-background"]
}"""


def analyze_with_llava(site_id: str) -> dict | None:
    site_dir = DATA_DIR / site_id
    img_path = site_dir / "screenshot_hero.png"

    if not img_path.exists():
        console.print(f"[yellow]⚠ No screenshot for[/yellow] {site_id}")
        return None

    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model":  OLLAMA_MODEL,
                "prompt": DESIGN_PROMPT,
                "images": [img_b64],
                "stream": False,
                "options": {"temperature": 0.1},  # low temp = more deterministic
            },
            timeout=120,
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("```")

        analysis = json.loads(raw)
        analysis["model"] = OLLAMA_MODEL
        analysis["parse_error"] = False

    except json.JSONDecodeError:
        console.print(f"[yellow]⚠ LLaVA JSON parse error for {site_id} — saving raw[/yellow]")
        analysis = {
            "raw_response": response.json().get("response", ""),
            "parse_error": True,
            "model": OLLAMA_MODEL,
        }
    except Exception as e:
        console.print(f"[red]✗ LLaVA failed for {site_id}: {e}[/red]")
        return None

    (site_dir / "llava_analysis.json").write_text(json.dumps(analysis, indent=2))
    console.print(
        f"[green]✓[/green] {site_id}: "
        f"{analysis.get('aesthetic_category','?')} / "
        f"{analysis.get('color_mood','?')} / "
        f"{analysis.get('motion_impression','?')}"
    )
    return analysis


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", help="Analyze a single site ID")
    args = parser.parse_args()

    console.print("[bold]Starting LLaVA analysis — make sure Ollama is running (`ollama serve`)[/bold]")

    if args.site:
        analyze_with_llava(args.site)
    else:
        for site_dir in sorted(DATA_DIR.iterdir()):
            if not site_dir.is_dir() or not (site_dir / "screenshot_hero.png").exists():
                continue
            if (site_dir / "llava_analysis.json").exists():
                console.print(f"[yellow]⏭ Skip[/yellow] {site_dir.name}")
                continue
            analyze_with_llava(site_dir.name)
            time.sleep(0.5)
