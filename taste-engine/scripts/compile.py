"""
compile.py — Step 7: Merge all data sources into master_dataset.jsonl.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from config import DATA_DIR, MASTER_FILE, ELO_FILE

console = Console()


def load_master() -> dict:
    """Load master dataset as a dict keyed by site_id."""
    entries = {}
    if MASTER_FILE.exists():
        for line in MASTER_FILE.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    e = json.loads(line)
                    entries[e["id"]] = e
                except Exception:
                    pass
    return entries


def save_master(entries: dict) -> None:
    """Write master dataset to JSONL file."""
    with open(MASTER_FILE, "w") as f:
        for entry in entries.values():
            f.write(json.dumps(entry) + "\n")


def compile_entry(site_id: str, elo_data: dict) -> dict | None:
    """Merge all per-site JSON files into one record."""
    site_dir = DATA_DIR / site_id

    if not site_dir.is_dir():
        return None

    entry = {"id": site_id}

    # ── Core data files ────────────────────────────────────────────────────
    for key, filename in [
        ("metadata",         "metadata.json"),
        ("visual",           "visual_analysis.json"),
        ("llava",            "llava_analysis.json"),
        ("motion_code",      "motion_code.json"),
        ("frames_manifest",  "frames_manifest.json"),
        ("design_rationale", "claude_rationale.json"),
    ]:
        path = site_dir / filename
        if path.exists():
            try:
                entry[key] = json.loads(path.read_text())
            except Exception:
                entry[key] = None
        else:
            entry[key] = None

    # ── Taste scores from Elo file ─────────────────────────────────────────
    entry["taste_score"] = elo_data.get(site_id, {
        "mu": None, "sigma": None, "conservative_score": None,
        "comparisons": 0, "consensus": None,
    })

    # ── Corpus eligibility flag ────────────────────────────────────────────
    ts = entry["taste_score"]
    entry["corpus_eligible"] = (
        ts.get("comparisons", 0) >= 5
        and ts.get("conservative_score") is not None
        and ts.get("conservative_score", 0) >= 10
    )

    return entry


def compile_all() -> int:
    """Recompile the entire master dataset from scratch."""
    # Load Elo scores
    elo_data = {}
    if ELO_FILE.exists():
        elo_data = json.loads(ELO_FILE.read_text())

    entries = {}
    for site_dir in sorted(DATA_DIR.iterdir()):
        if not site_dir.is_dir() or site_dir.name.startswith("."):
            continue
        site_id = site_dir.name
        entry   = compile_entry(site_id, elo_data)
        if entry:
            entries[site_id] = entry

    save_master(entries)
    return len(entries)


if __name__ == "__main__":
    count = compile_all()
    console.print(f"[green]✓ Master dataset compiled: {count} entries → {MASTER_FILE}[/green]")

    # Quick stats
    entries = load_master()
    with_rationale  = sum(1 for e in entries.values() if e.get("design_rationale"))
    with_motion     = sum(1 for e in entries.values() if e.get("motion_code"))
    with_frames     = sum(1 for e in entries.values() if e.get("frames_manifest"))
    with_elo        = sum(1 for e in entries.values() if e.get("taste_score", {}).get("mu"))
    corpus_eligible = sum(1 for e in entries.values() if e.get("corpus_eligible"))

    console.print(f"\n[bold]Dataset Status:[/bold]")
    console.print(f"  Total entries:        {count}")
    console.print(f"  With visual analysis: {sum(1 for e in entries.values() if e.get('visual'))}")
    console.print(f"  With motion code:     {with_motion}")
    console.print(f"  With frame sequence:  {with_frames}")
    console.print(f"  With Claude rationale:{with_rationale}")
    console.print(f"  With Elo scores:      {with_elo}")
    console.print(f"  [green]Corpus eligible:      {corpus_eligible}[/green]")
