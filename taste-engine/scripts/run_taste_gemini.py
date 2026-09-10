"""
run_taste_gemini.py — Taste Extraction via Gemini API
Separate script so extract_taste.py stays untouched.

Uses GEMINI_API_KEY from .env to call gemini-2.0-flash via litellm.
"""
import sys
import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv

# Load .env from taste-engine root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from rich.console import Console
from litellm import completion
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import METADATA_FILE, VISUAL_FILE, RATIONALE_FILE

console = Console()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_KEY:
    console.print("[red]GEMINI_API_KEY not found in .env![/red]")
    sys.exit(1)

os.environ["GEMINI_API_KEY"] = GEMINI_KEY


def get_site_ids_from_json(filepath: Path) -> list:
    """Extract site IDs from summary JSON files."""
    if not filepath.exists():
        return []
    content = filepath.read_text()
    # Try JSON array first
    try:
        data = json.loads(content)
        if isinstance(data, list):
            ids = []
            for item in data:
                if isinstance(item, dict) and "site_id" in item:
                    ids.append(item["site_id"])
            if ids:
                return list(dict.fromkeys(ids))
    except json.JSONDecodeError:
        pass
    # Fallback: regex match site-XXX
    sites = re.findall(r"(site-\d{3})", content)
    return list(dict.fromkeys(sites))


def build_markdown_table(site_ids, data_dir: Path) -> str:
    """Builds a dense Markdown table of statistical metrics."""
    headers = [
        "Site ID", "Nodes", "WS Ratio", "Asymmetry",
        "Color Var", "Dom Brightness", "Pal Mood", "Scroll Depth", "Style Tags"
    ]

    rows = []
    for site_id in site_ids:
        meta_path = data_dir / site_id / METADATA_FILE
        visual_path = data_dir / site_id / VISUAL_FILE
        rationale_path = data_dir / site_id / RATIONALE_FILE

        if not meta_path.exists() or not visual_path.exists() or not rationale_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_text())
            visual = json.loads(visual_path.read_text())
            try:
                rationale = json.loads(rationale_path.read_text())
                tags = rationale.get('style_tags', [])
                style_str = ", ".join(tags) if tags else "N/A"
            except Exception:
                style_str = "N/A"

            nodes = meta.get("dom_structure", {}).get("tags", {}).get("total_nodes", "N/A")
            ws_ratio = f"{visual.get('whitespace_ratio', 0):.3f}"
            asym = f"{visual.get('asymmetry_score', 0):.3f}"
            c_var = f"{visual.get('color_variance', 0):.3f}"
            brightness = f"{visual.get('dominant_color', {}).get('brightness', 0):.3f}"
            mood = visual.get('palette_mood', "N/A")
            scroll = f"{visual.get('scroll_depth_multiplier', 0):.1f}"

            rows.append(f"| {site_id} | {nodes} | {ws_ratio} | {asym} | {c_var} | {brightness} | {mood} | {scroll} | {style_str} |")
        except Exception as e:
            console.print(f"[yellow]Skipping {site_id}: {e}[/yellow]")

    if not rows:
        return "(no data found)"

    header_str = "| " + " | ".join(headers) + " |\n"
    header_str += "|" + "|".join(["---" for _ in headers]) + "|\n"
    return header_str + "\n".join(rows)


def run_llm(prompt: str, label: str) -> str:
    """Calls local ollama/gemma4 via litellm."""
    console.print(f"\n[bold cyan]Calling ollama/gemma4 (local) for: {label}...[/bold cyan]")
    try:
        response = completion(
            model="ollama/gemma4",
            messages=[{"role": "user", "content": prompt}],
            api_base="http://localhost:11434",
            max_tokens=4096,
            stream=True
        )

        full_text = ""
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            sys.stdout.write(delta)
            sys.stdout.flush()
            full_text += delta

        print("\n")
        return full_text
    except Exception as e:
        console.print(f"\n[red]Gemini API Error: {e}[/red]")
        return ""


def main():
    base_dir = Path(__file__).parent.parent
    results_dir = base_dir / "results"
    data_dir = base_dir / "data"

    winners_path = results_dir / "winners_summaries.json"
    losers_path = results_dir / "losers_summaries.json"

    if not winners_path.exists() or not losers_path.exists():
        console.print("[red]Could not find winners_summaries.json or losers_summaries.json![/red]")
        sys.exit(1)

    winner_ids = get_site_ids_from_json(winners_path)
    loser_ids = get_site_ids_from_json(losers_path)

    console.print(f"[cyan]Found {len(winner_ids)} Winners and {len(loser_ids)} Losers.[/cyan]")

    # ── MAP PHASE ─────────────────────────────────────────────────────────────
    console.print("\n[cyan]═══ MAP: Building Deterministic Tables ═══[/cyan]")
    winner_table = build_markdown_table(winner_ids, data_dir)
    loser_table = build_markdown_table(loser_ids, data_dir)

    console.print(f"\n[dim]Winner table rows: {winner_table.count('site-')}[/dim]")
    console.print(f"[dim]Loser table rows:  {loser_table.count('site-')}[/dim]")

    # ── REDUCE PHASE ──────────────────────────────────────────────────────────
    console.print("\n[cyan]═══ REDUCE: Synthesizing Rules of Taste via Gemini ═══[/cyan]")

    reduce_prompt = f"""You are the world's leading expert in digital design and structural aesthetics.
I am providing you with two statistical tables containing visual mechanics data for the Highest Rated websites (Winners) and the Lowest Rated websites (Losers).

Your task is to synthesize these metrics into the definitive "Rules of Taste". Analyze the data differences between Winners and Losers to derive your conclusions.

TOP TIER (WINNERS) STATS:
{winner_table}

BOTTOM TIER (LOSERS) STATS:
{loser_table}

Output a comprehensive Markdown report covering:
1. **Core Differences** — Visual, mathematical, and structural differences observed in the data
2. **Structural Systems** — Typography, whitespace, asymmetry, DOM density patterns
3. **Aesthetic Elements** — Color variance, palette moods, brightness patterns
4. **The Definitive "Taste Tokens"** — Highly specific, actionable rules to achieve top-tier aesthetics based on the statistical indicators of the Winners

Output the final Markdown report directly. No conversational filler."""

    final_report = run_llm(reduce_prompt, "Final Rules of Taste Synthesis")

    if final_report:
        out_file = results_dir / "taste_extraction_report.md"
        out_file.write_text(final_report)
        console.print(f"\n[bold green]✓ Report saved to {out_file}[/bold green]")
    else:
        console.print("[red]Failed to generate report.[/red]")


if __name__ == "__main__":
    main()
