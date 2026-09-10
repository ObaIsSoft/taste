#!/usr/bin/env python3
"""
pipeline.py — Master orchestrator. Run the full TASTE pipeline for all sites.

Usage:
  python pipeline.py                  # Full pipeline, all sites
  python pipeline.py --site site-001  # Single site
  python pipeline.py --from step3     # Resume from a specific step
  python pipeline.py --status         # Show what's done for each site

Steps (canonical, Plan A freeze):
  1. scrape      → screenshots + video + motion code (scripts/scraper.py)
  2. frames      → extract keyframes via preprocess_video → frames/ + motion_storyboard.json
  3. visual      → color DNA via analyzer → visual_analysis.json
  4. llava       → DEPRECATED legacy (llava_analysis.json). Kept for compat only.
  5. enrich      → local VLM+reasoner via enrich.py → taste_rationale.json + stage2_vlm_raw.json
  6. embed       → nomic-embed-text via embed_rationale.py → embedding.json
  7. compile     → merge everything into master_dataset.jsonl
  8. validate    → pairwise TrueSkill session (Supabase is source of truth)
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
    METADATA_FILE, VISUAL_FILE, MOTION_CODE_FILE, STORYBOARD_FILE,
    FRAMES_DIRNAME, RATIONALE_FILE, VLM_RAW_FILE, EMBED_FILE,
    LEGACY_LLAVA,
)

console = Console()

STEPS = ["scrape", "frames", "visual", "llava", "enrich", "embed", "compile", "validate"]


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

        elif step == "frames":
            from scripts.preprocess_video import process_video
            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / METADATA_FILE).exists():
                    continue
                if (d / STORYBOARD_FILE).exists() and (d / FRAMES_DIRNAME).is_dir():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                process_video(d.name)

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

        elif step == "llava":
            console.print("[yellow]DEPRECATED: llava step writes legacy llava_analysis.json only. Use enrich instead.[/yellow]")
            from scripts.vision_llm import analyze_with_llava
            import requests as req
            # Check Ollama is running
            try:
                req.get("http://localhost:11434", timeout=3)
            except Exception:
                console.print("[red]✗ Ollama not running. Start with: ollama serve[/red]")
                return False

            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / "screenshot_hero.png").exists():
                    continue
                if (d / LEGACY_LLAVA).exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                analyze_with_llava(d.name)
                time.sleep(0.5)

        elif step == "enrich":
            from scripts.enrich import enrich_with_claude
            from scripts.compile import load_master, save_master
            entries = load_master()
            targets = [site_id] if site_id else list(entries.keys())
            # Fall back to DATA_DIR scan when master is empty (fresh checkout)
            if not targets:
                targets = [d.name for d in sorted(DATA_DIR.iterdir())
                           if d.is_dir() and (d / METADATA_FILE).exists()
                           and (site_id is None or d.name == site_id)]
            for sid in targets:
                if (DATA_DIR / sid / RATIONALE_FILE).exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {sid}")
                    continue
                result = enrich_with_claude(sid, entries.get(sid, {}))
                if result:
                    if sid not in entries:
                        entries[sid] = {"id": sid}
                    entries[sid]["design_rationale"] = result
                    save_master(entries)
                time.sleep(2)

        elif step == "embed":
            from scripts.embed_rationale import generate_embedding
            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / RATIONALE_FILE).exists():
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
    table = Table(title="TASTE Pipeline Status (canonical)", box=box.ROUNDED)
    table.add_column("Site ID",  style="cyan")
    table.add_column("Scraped",  justify="center")
    table.add_column("Video",    justify="center")
    table.add_column("Storyboard", justify="center")
    table.add_column("Visual",   justify="center")
    table.add_column("Rationale", justify="center")
    table.add_column("Embed",    justify="center")
    table.add_column("Elo",      justify="center")

    from config import ELO_FILE
    import json
    elo_data = json.loads(ELO_FILE.read_text()) if ELO_FILE.exists() else {}

    for site_dir in sorted(DATA_DIR.iterdir()):
        if not site_dir.is_dir():
            continue
        sid = site_dir.name

        def check(filename): return "✅" if (site_dir / filename).exists() else "❌"
        has_video  = bool(list(site_dir.glob("*.webm")))
        has_elo    = "✅" if sid in elo_data else "❌"

        table.add_row(
            sid,
            check(METADATA_FILE),
            "✅" if has_video else "❌",
            check(STORYBOARD_FILE),
            check(VISUAL_FILE),
            check(RATIONALE_FILE),
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
