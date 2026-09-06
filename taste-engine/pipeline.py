#!/usr/bin/env python3
"""
pipeline.py — Master orchestrator. Run the full TASTE pipeline for all sites.

Usage:
  python pipeline.py                  # Full pipeline, all sites
  python pipeline.py --site site-001  # Single site
  python pipeline.py --from step3     # Resume from a specific step
  python pipeline.py --status         # Show what's done for each site

Steps:
  1. scrape      → screenshots + video + motion code
  2. frames      → extract keyframes from video
  3. visual      → color DNA, brightness, palette
  4. llava       → local vision model classification
  5. enrich      → Claude deep analysis (costs money)
  6. compile     → merge everything into master_dataset.jsonl
  7. validate    → pairwise Elo comparison session (interactive)
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

from config import DATA_DIR, MASTER_FILE, ANTHROPIC_API_KEY

console = Console()

STEPS = ["scrape", "frames", "visual", "llava", "enrich", "compile", "validate"]


def run_step(step: str, site_id: str | None = None) -> bool:
    """Run a single pipeline step."""
    console.rule(f"[bold]Step: {step}[/bold]")

    try:
        if step == "scrape":
            from scripts.scraper import scrape_site, SITES
            targets = [s for s in SITES if site_id is None or s["id"] == site_id]
            for s in targets:
                if (DATA_DIR / s["id"] / "metadata.json").exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {s['id']}")
                    continue
                scrape_site(s["url"], s["id"])
                time.sleep(2)

        elif step == "frames":
            from scripts.motion_capture import extract_frames
            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / "metadata.json").exists():
                    continue
                if (d / "frames_manifest.json").exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                extract_frames(d.name)

        elif step == "visual":
            from scripts.analyzer import analyze_image
            dirs = [DATA_DIR / site_id] if site_id else sorted(DATA_DIR.iterdir())
            for d in dirs:
                if not isinstance(d, Path):
                    d = DATA_DIR / d
                if not d.is_dir() or not (d / "screenshot_hero.png").exists():
                    continue
                if (d / "visual_analysis.json").exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                analyze_image(d.name)

        elif step == "llava":
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
                if (d / "llava_analysis.json").exists():
                    console.print(f"[yellow]⏭ Skip[/yellow] {d.name}")
                    continue
                analyze_with_llava(d.name)
                time.sleep(0.5)

        elif step == "enrich":
            if not ANTHROPIC_API_KEY:
                console.print("[red]✗ ANTHROPIC_API_KEY not set in .env[/red]")
                return False

            from scripts.enrich_claude import enrich_with_claude
            from scripts.compile import load_master, save_master
            entries = load_master()
            targets = [site_id] if site_id else list(entries.keys())
            for sid in targets:
                if entries.get(sid, {}).get("design_rationale"):
                    console.print(f"[yellow]⏭ Skip[/yellow] {sid}")
                    continue
                result = enrich_with_claude(sid, entries.get(sid, {}))
                if result:
                    if sid not in entries:
                        entries[sid] = {"id": sid}
                    entries[sid]["design_rationale"] = result
                    save_master(entries)
                time.sleep(2)

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
    table = Table(title="TASTE Pipeline Status", box=box.ROUNDED)
    table.add_column("Site ID",  style="cyan")
    table.add_column("Scraped",  justify="center")
    table.add_column("Video",    justify="center")
    table.add_column("Frames",   justify="center")
    table.add_column("Visual",   justify="center")
    table.add_column("LLaVA",    justify="center")
    table.add_column("Claude",   justify="center")
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
            check("metadata.json"),
            "✅" if has_video else "❌",
            check("frames_manifest.json"),
            check("visual_analysis.json"),
            check("llava_analysis.json"),
            check("claude_rationale.json"),
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
