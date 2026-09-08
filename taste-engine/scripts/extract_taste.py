"""
extract_taste.py — Phase 2: The Taste Extractor (Statistical Table Reduce)

Extracts visual and metadata metrics to a dense Markdown table, then uses the
powerful free-claude-code proxy to synthesize the final "Rules of Taste".
"""
import sys
import os
import json
import re
from pathlib import Path
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent.parent))
from litellm import completion

console = Console()

def get_site_ids_from_text(filepath: Path) -> list:
    """Regex match --- SITE site-XXX ANALYSIS --- from text"""
    if not filepath.exists():
        return []
    content = filepath.read_text()
    # Find all site-XXX
    sites = re.findall(r"--- SITE (site-\d{3})", content)
    # Deduplicate and keep order
    return list(dict.fromkeys(sites))

def build_markdown_table(site_ids, data_dir: Path) -> str:
    """Builds a dense Markdown table of statistical metrics for the given sites."""
    headers = [
        "Site ID", "Nodes", "WS Ratio", "Asymmetry", 
        "Color Var", "Dom Brightness", "Pal Mood", "Scroll Depth", "Motion Shifts"
    ]
    
    rows = []
    
    for site_id in site_ids:
        meta_path = data_dir / site_id / "metadata.json"
        visual_path = data_dir / site_id / "visual_analysis.json"
        motion_path = data_dir / site_id / "motion_storyboard.json"
        
        if not meta_path.exists() or not visual_path.exists():
            continue
            
        try:
            meta = json.loads(meta_path.read_text())
            visual = json.loads(visual_path.read_text())
            
            motion_shifts = "0"
            if motion_path.exists():
                try:
                    motion = json.loads(motion_path.read_text())
                    motion_shifts = str(motion.get("total_extracted", 0))
                except Exception:
                    pass
            
            nodes = meta.get("dom_structure", {}).get("tags", {}).get("total_nodes", "N/A")
            ws_ratio = f"{visual.get('whitespace_ratio', 0):.3f}"
            asym = f"{visual.get('asymmetry_score', 0):.3f}"
            c_var = f"{visual.get('color_variance', 0):.3f}"
            brightness = f"{visual.get('dominant_color', {}).get('brightness', 0):.3f}"
            mood = visual.get('palette_mood', "N/A")
            scroll = f"{visual.get('scroll_depth_multiplier', 0):.1f}"
            
            rows.append(f"| {site_id} | {nodes} | {ws_ratio} | {asym} | {c_var} | {brightness} | {mood} | {scroll} | {motion_shifts} |")
        except Exception as e:
            console.print(f"[yellow]Skipping {site_id} due to parse error: {e}[/yellow]")
            
    header_str = "| " + " | ".join(headers) + " |\n"
    header_str += "|" + "|".join(["---" for _ in headers]) + "|\n"
    
    return header_str + "\n".join(rows)

def stream_completion(prompt, label):
    """Runs a completion via the free-claude-code proxy."""
    console.print(f"\n[bold yellow]Generating {label} via FCC Proxy...[/bold yellow]")
    try:
        # litellm will use the OpenAI API interface when model starts with openai/
        # the model name will be intercepted by the FCC proxy.
        response = completion(
            model="llama-3.1-nemotron-70b-instruct",
            messages=[{"role": "user", "content": prompt}],
            api_base="http://127.0.0.1:8082/v1",
            api_key="freecc",
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
        console.print(f"\n[red]Error connecting to Proxy: {e}[/red]")
        console.print("[yellow]Hint: Ensure `fcc-server` is running on port 8082![/yellow]")
        return ""

def main():
    base_dir = Path(__file__).parent.parent
    results_dir = base_dir / "results"
    data_dir = base_dir / "data"
    
    winners_path = results_dir / "winners_summaries.json"
    losers_path = results_dir / "losers_summaries.json"
    
    if not winners_path.exists() or not losers_path.exists():
        console.print("[red]Could not find summaries![/red]")
        sys.exit(1)
        
    winner_ids = get_site_ids_from_text(winners_path)
    loser_ids = get_site_ids_from_text(losers_path)
    
    console.print(f"[cyan]Found {len(winner_ids)} Winners and {len(loser_ids)} Losers.[/cyan]")
    
    # ── MAP PHASE: Build Statistical Tables ───────────────────────────────────
    console.print("\n[cyan]=== MAP: Generating Deterministic Tables ===[/cyan]")
    winner_table = build_markdown_table(winner_ids, data_dir)
    loser_table = build_markdown_table(loser_ids, data_dir)
    
    # ── REDUCE PHASE: Final Synthesis via Proxy ──────────────────────────────
    console.print("\n[cyan]=== REDUCE: Final Synthesis ===[/cyan]")
    
    reduce_prompt = f"""
You are the world's leading expert in digital design and structural aesthetics.
I am providing you with two highly detailed statistical tables containing visual mechanics data for the Highest Rated websites (The Winners) and the Lowest Rated websites (The Losers).

Your task is to synthesize these metrics into the definitive "Rules of Taste". Look at the data differences between Winners and Losers to inform your conclusions.

TOP TIER (THE WINNERS) STATS:
{winner_table}

BOTTOM TIER (THE LOSERS) STATS:
{loser_table}

Output a comprehensive Markdown report that covers:
1. The Core Differences (Visual, Mathematical, and Structural differences observed in the data)
2. Structural Systems (Typography, Whitespace, Asymmetry, DOM Density)
3. Aesthetic Elements (Color Variance, Palette Moods, Brightness)
4. The Definitive "Taste Tokens" (Highly specific, actionable rules to achieve a top-tier aesthetic based on the statistical indicators of the Winners)

Just output the final Markdown report directly. Do not output conversational filler.
"""
    
    final_report = stream_completion(reduce_prompt, "Final Rules of Taste Synthesis")
    
    if final_report:
        out_file = results_dir / "taste_extraction_report.md"
        out_file.write_text(final_report)
        console.print(f"\n[green]✓ Analysis complete! Saved to {out_file}[/green]")
    else:
        console.print("[red]Failed to generate report.[/red]")

if __name__ == "__main__":
    main()
