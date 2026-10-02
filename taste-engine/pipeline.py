#!/usr/bin/env python3
"""
pipeline.py — Master orchestrator. Run the full TASTE pipeline for all sites.

Usage:
  python pipeline.py                  # Full pipeline, all sites
  python pipeline.py --site site-001  # Single site
  python pipeline.py --from step3     # Resume from a specific step
  python pipeline.py --status         # Show what's done for each site

Steps (canonical, v2):
  1. scrape      → 2 screenshots + motion code + metadata (scripts/scraper.py)
  2. visual      → color DNA via analyzer → visual_analysis.json
  3. vlm         → forensic VLM features via enrich.py → stage2_vlm_raw.json (FEATURE, not label)
  4. embed       → nomic-embed-text via embed_rationale.py → embedding.json
  5. compile     → merge everything into master_dataset.jsonl
  6. validate    → pairwise TrueSkill session (Supabase is source of truth)

Removed steps (v1 → v2):
  - preprocess_video (video keyframe extraction — no longer needed)
  - llava (deprecated legacy)
  - enrich rationale generation (VLM confabulation — replaced by voter reasoning)
"""

import sys
import time
import argparse
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import box

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DATA_DIR, MASTER_FILE,
    METADATA_FILE, VISUAL_FILE, MOTION_CODE_FILE,
    VLM_RAW_FILE, EMBED_FILE,
)

console = Console()

STEPS = ["scrape", "visual", "vlm", "embed", "compile", "validate"]


def run_step(step: str, site_id: str | None = None) -> bool:
    """Run a single pipeline step."""
    console.rule(f"[bold]Step: {step}[/bold]")

    try:
        if step == "scrape":
            from scripts.scraper import scrape_site, SITES
            targets = [s for s in SITES if site_id is None or s["id"] == site_id]
            for s in targets:
                if (DATA_DIR / s["id"] / METADATA_FILE).exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {s['id']}")
                    continue
                scrape_site(s["url"], s["id"])
                time.sleep(2)

        elif step == "visual":
            from scripts.analyzer import analyze_image
            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / "screenshot_hero.png").exists():
                    continue
                if (d / VISUAL_FILE).exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                analyze_image(d.name)

        elif step == "vlm":
            from scripts.enrich import extract_vlm_features
            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / "screenshot_hero.png").exists():
                    continue
                if (d / VLM_RAW_FILE).exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                extract_vlm_features(d.name)
                time.sleep(1)

        elif step == "embed":
            from scripts.embed_rationale import generate_embedding
            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / VLM_RAW_FILE).exists():
                    continue
                if (d / EMBED_FILE).exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                generate_embedding(d.name)
                time.sleep(1)

        elif step == "compile":
            from scripts.compile import compile_all
            count = compile_all()
            console.print(f"[green]✓ Compiled {count} entries[/green]")

        elif step == "validate":
            from scripts.elo_validator import run_comparison_session
            run_comparison_session()

        return True

    except Exception as e:
        console.print(f"[red]✗ Step '{step}' failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False


def show_status() -> None:
    """Show what pipeline steps are complete for each site."""
    table = Table(title="TASTE Pipeline Status (v2)", box=box.ROUNDED)
    table.add_column("Site ID",  style="cyan")
    table.add_column("Scraped",  justify="center")
    table.add_column("Visual",   justify="center")
    table.add_column("VLM",      justify="center")
    table.add_column("Embed",   justify="center")
    table.add_column("Elo",      justify="center")

    from config import ELO_FILE
    import json
    elo_data = json.loads(ELO_FILE.read_text()) if ELO_FILE.exists() else {}

    for site_dir in sorted(DATA_DIR.iterdir()):
        if not site_dir.is_dir():
            continue
        sid = site_dir.name

        def check(filename): return "✅" if (site_dir / filename).exists() else "❌"
        has_elo    = "✅" if sid in elo_data else "❌"

        table.add_row(
            sid,
            check(METADATA_FILE),
            check(VISUAL_FILE),
            check(VLM_RAW_FILE),
            check(EMBED_FILE),
            has_elo,
        )

    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TASTE Pipeline Orchestrator")
    parser.add_argument("--site",   help="Run pipeline for a single site ID")
    parser.add_argument("--from",   dest="from_step", choices=STEPS, help="Start from this step")
    parser.add_argument("--only",   choices=STEPS, help="Run only this step")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    args = parser.parse_args()

    if args.status:
        show_status()
        sys.exit(0)

    steps_to_run = STEPS
    if args.only:
        steps_to_run = [args.only]
    elif args.from_step:
        start_idx    = STEPS.index(args.from_step)
        steps_to_run = STEPS[start_idx:]

    console.print(f"[bold]TASTE Pipeline[/bold] — steps: {' → '.join(steps_to_run)}")
    if args.site:
        console.print(f"[bold]Site:[/bold] {args.site}")

    for step in steps_to_run:
        if step == "validate":
            # Always interactive — don't skip
            run_step("validate", args.site)
        else:
            success = run_step(step, args.site)
            if not success and step in ("scrape", "enrich"):
                console.print(f"[red]Critical step failed. Stopping.[/red]")
                break

    console.print("\n[bold green]Pipeline run complete.[/bold green]")
    show_status()
