"""
elo_validator.py — Step 6: Pairwise preference system replacing 1–10 scoring.
"""
import sys
import json
import random
import time
import os
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
import trueskill
from config import (
    DATA_DIR, ELO_FILE, MIN_COMPARISONS,
    METADATA_FILE, RATIONALE_FILE, EMBED_FILE,
)

console = Console()

# TrueSkill environment (default: mu=25, sigma=8.333)
env = trueskill.TrueSkill(draw_probability=0.1)


# ── Persistence ────────────────────────────────────────────────────────────

def load_ratings() -> dict:
    """Load existing ratings from file."""
    if ELO_FILE.exists():
        data = json.loads(ELO_FILE.read_text())
        # Reconstruct TrueSkill Rating objects
        return {
            sid: {
                "rating": env.create_rating(
                    mu=r["mu"], sigma=r["sigma"]
                ),
                "comparisons": r["comparisons"],
                "wins": r["wins"],
                "losses": r["losses"],
                "draws": r["draws"],
                "history": r.get("history", []),
            }
            for sid, r in data.items()
        }
    return {}


def save_ratings(ratings: dict) -> None:
    """Serialize and save ratings."""
    data = {
        sid: {
            "mu":          r["rating"].mu,
            "sigma":       r["rating"].sigma,
            "conservative_score": round(r["rating"].mu - 3 * r["rating"].sigma, 2),
            "comparisons": r["comparisons"],
            "wins":        r["wins"],
            "losses":      r["losses"],
            "draws":       r["draws"],
            "consensus":   round(1 - (r["rating"].sigma / 8.333), 3),  # 1 = total agreement
            "history":     r["history"][-50:],  # keep last 50 results
        }
        for sid, r in ratings.items()
    }
    ELO_FILE.write_text(json.dumps(data, indent=2))


def init_rating_for_site(site_id: str, ratings: dict) -> None:
    """Add a new site with default rating if not present."""
    if site_id not in ratings:
        ratings[site_id] = {
            "rating":      env.create_rating(),  # mu=25, sigma=8.333
            "comparisons": 0,
            "wins":        0,
            "losses":      0,
            "draws":       0,
            "history":     [],
        }


# ── Comparison session ─────────────────────────────────────────────────────

def get_sites_to_compare() -> list[str]:
    """Get all site IDs that have rationale JSON (ready for evaluation)."""
    sites = []
    for site_dir in DATA_DIR.iterdir():
        if site_dir.is_dir() and (site_dir / RATIONALE_FILE).exists():
            sites.append(site_dir.name)
    return sorted(sites)


def cosine_similarity(v1, v2):
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def pick_pair(ratings: dict, all_sites: list[str]) -> tuple[str, str] | None:
    """
    Smart pair selection:
    - Prefer pairs where one or both sites have fewer comparisons (explore first)
    - Avoid pairs that have already been compared
    - Use Cosine Similarity on embeddings to find visually similar matchups
    """
    if len(all_sites) < 2:
        return None

    # Sort by comparisons ascending — compare least-seen sites first
    sorted_sites = sorted(all_sites, key=lambda s: ratings.get(s, {}).get("comparisons", 0))

    # Load embeddings
    embeddings = {}
    for s in all_sites:
        emb_path = DATA_DIR / s / EMBED_FILE
        if emb_path.exists():
            embeddings[s] = json.loads(emb_path.read_text()).get("vector", [])
        else:
            embeddings[s] = []

    # Try to find a pair that hasn't been compared yet
    for anchor in sorted_sites:
        anchor_history = [h["vs"] for h in ratings.get(anchor, {}).get("history", [])]
        
        # Pool of opponents anchor hasn't faced yet
        pool = [s for s in all_sites if s != anchor and s not in anchor_history]
        
        if pool:
            # Sort pool by embedding similarity to anchor (highest first)
            anchor_emb = embeddings[anchor]
            if anchor_emb:
                pool.sort(key=lambda s: cosine_similarity(anchor_emb, embeddings[s]), reverse=True)
            else:
                # Fallback to similar rating if embeddings not found
                anchor_mu = ratings.get(anchor, {}).get("rating", env.create_rating()).mu
                pool.sort(key=lambda s: abs(ratings.get(s, {}).get("rating", env.create_rating()).mu - anchor_mu))
                
            return anchor, pool[0]

    # If all pairs have been exhausted, return None to end the session early
    return None


def load_display_info(site_id: str) -> dict:
    """Load metadata and rationale for display during comparison."""
    site_dir = DATA_DIR / site_id
    info = {"id": site_id, "title": site_id, "url": "", "tags": []}

    meta_path = site_dir / METADATA_FILE
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        info["title"] = meta.get("title", site_id)
        info["url"]   = meta.get("url", "")

    rationale_path = site_dir / RATIONALE_FILE
    if rationale_path.exists():
        try:
            rat = json.loads(rationale_path.read_text())
            rat_text = rat.get("taste_rule", "") or json.dumps(rat)[:400]
        except Exception:
            rat_text = rationale_path.read_text()[:400]
        info["rationale_excerpt"] = rat_text[:400] + "..."
    else:
        info["rationale_excerpt"] = "No rationale generated yet."

    return info


def show_comparison(site_a: dict, site_b: dict) -> None:
    """Display the two sites for comparison."""
    console.print("\n")
    console.rule("[bold yellow]⚡ TASTE COMPARISON[/bold yellow]")

    # Site A
    console.print(Panel(
        f"[bold cyan]{site_a['title']}[/bold cyan]\n"
        f"[dim]{site_a['url']}[/dim]\n\n"
        f"Tags: {', '.join(site_a['tags'][:5])}\n"
        f"Motion: {site_a.get('motion', '?')}\n"
        f"Signals: {', '.join(site_a.get('signals', []))}\n\n"
        f"[italic]{site_a.get('rationale_excerpt', '')}[/italic]",
        title="[A] Site A",
        border_style="cyan",
    ))

    # Site B
    console.print(Panel(
        f"[bold magenta]{site_b['title']}[/bold magenta]\n"
        f"[dim]{site_b['url']}[/dim]\n\n"
        f"Tags: {', '.join(site_b['tags'][:5])}\n"
        f"Motion: {site_b.get('motion', '?')}\n"
        f"Signals: {', '.join(site_b.get('signals', []))}\n\n"
        f"[italic]{site_b.get('rationale_excerpt', '')}[/italic]",
        title="[B] Site B",
        border_style="magenta",
    ))


def run_comparison_session(max_rounds: int = 20) -> None:
    """
    Interactive pairwise comparison session.
    Opens screenshot previews in the terminal if possible.
    """
    all_sites = get_sites_to_compare()
    if len(all_sites) < 2:
        console.print("[red]Need at least 2 enriched sites to compare.[/red]")
        return

    ratings = load_ratings()
    for sid in all_sites:
        init_rating_for_site(sid, ratings)

    console.print(f"[bold]TASTE Pairwise Validator[/bold] — {len(all_sites)} sites available")
    console.print("For each pair, choose which feels more PREMIUM and INTENTIONAL.\n")
    console.print("Controls: [cyan]A[/cyan] = prefer A  |  [magenta]B[/magenta] = prefer B  |  [yellow]D[/yellow] = draw/tie  |  [dim]S[/dim] = skip  |  [red]Q[/red] = quit\n")

    rounds_done = 0
    while rounds_done < max_rounds:
        pair = pick_pair(ratings, all_sites)
        if not pair:
            console.print("[yellow]No more pairs to compare.[/yellow]")
            break

        sid_a, sid_b = pair
        info_a = load_display_info(sid_a)
        info_b = load_display_info(sid_b)

        show_comparison(info_a, info_b)

        # Try to open screenshots side by side in browser
        path_a = DATA_DIR / sid_a / "screenshot_hero.png"
        path_b = DATA_DIR / sid_b / "screenshot_hero.png"
        if path_a.exists() and path_b.exists():
            html_content = f"""
            <html>
            <body style="background:#111; color:white; display:flex; gap:20px; font-family:sans-serif; padding: 20px;">
                <div style="flex:1; text-align:center;">
                    <h2 style="color: cyan;">[A] {info_a['title']}</h2>
                    <img src="file://{path_a.absolute()}" style="max-width:100%; border: 2px solid cyan; border-radius: 8px;">
                </div>
                <div style="flex:1; text-align:center;">
                    <h2 style="color: magenta;">[B] {info_b['title']}</h2>
                    <img src="file://{path_b.absolute()}" style="max-width:100%; border: 2px solid magenta; border-radius: 8px;">
                </div>
            </body>
            </html>
            """
            html_path = DATA_DIR / "comparison.html"
            html_path.write_text(html_content)
            console.print(f"[dim]Screenshots: Opening side-by-side preview in your web browser...[/dim]")
            os.system(f"open '{html_path}' 2>/dev/null")

        choice = input("\nYour choice [A/B/D/S/Q]: ").strip().upper()

        if choice == "Q":
            break
        elif choice == "S":
            console.print("[dim]Skipped[/dim]")
            continue
        elif choice not in ("A", "B", "D"):
            console.print("[yellow]Invalid input — skipping[/yellow]")
            continue

        # ── Update TrueSkill ratings ───────────────────────────────────────
        rating_a = ratings[sid_a]["rating"]
        rating_b = ratings[sid_b]["rating"]

        if choice == "A":
            new_a, new_b = env.rate_1vs1(rating_a, rating_b)
            ratings[sid_a]["wins"]   += 1
            ratings[sid_b]["losses"] += 1
            winner = sid_a
        elif choice == "B":
            new_b, new_a = env.rate_1vs1(rating_b, rating_a)
            ratings[sid_b]["wins"]   += 1
            ratings[sid_a]["losses"] += 1
            winner = sid_b
        else:  # Draw
            new_a, new_b = env.rate_1vs1(rating_a, rating_b, drawn=True)
            ratings[sid_a]["draws"]  += 1
            ratings[sid_b]["draws"]  += 1
            winner = "draw"

        ratings[sid_a]["rating"]      = new_a
        ratings[sid_b]["rating"]      = new_b
        ratings[sid_a]["comparisons"] += 1
        ratings[sid_b]["comparisons"] += 1

        # Record history
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        ratings[sid_a]["history"].append({"vs": sid_b, "result": "win" if winner == sid_a else ("draw" if winner == "draw" else "loss"), "ts": ts})
        ratings[sid_b]["history"].append({"vs": sid_a, "result": "win" if winner == sid_b else ("draw" if winner == "draw" else "loss"), "ts": ts})

        save_ratings(ratings)

        console.print(
            f"[green]✓[/green] Recorded: "
            f"[cyan]{sid_a}[/cyan] μ={new_a.mu:.1f}σ={new_a.sigma:.1f} | "
            f"[magenta]{sid_b}[/magenta] μ={new_b.mu:.1f}σ={new_b.sigma:.1f}"
        )
        rounds_done += 1

    console.print(f"\n[bold]Session complete. {rounds_done} comparisons recorded.[/bold]")
    show_rankings(ratings)


# ── Rankings report ────────────────────────────────────────────────────────

def show_rankings(ratings: dict | None = None) -> None:
    if ratings is None:
        ratings = load_ratings()

    if not ratings:
        console.print("[yellow]No ratings yet.[/yellow]")
        return

    # Sort by conservative score (mu - 3*sigma) — penalises uncertainty
    sorted_sites = sorted(
        ratings.items(),
        key=lambda x: x[1]["rating"].mu - 3 * x[1]["rating"].sigma,
        reverse=True,
    )

    table = Table(title="🏆 TASTE Rankings", box=box.ROUNDED, show_lines=True)
    table.add_column("Rank", style="bold", width=4)
    table.add_column("Site ID", style="cyan")
    table.add_column("Title", width=25)
    table.add_column("Score (μ-3σ)", justify="right", style="green")
    table.add_column("Mu", justify="right")
    table.add_column("Sigma", justify="right")
    table.add_column("Consensus", justify="right")
    table.add_column("Comparisons", justify="right")
    table.add_column("Corpus?", justify="center")

    for rank, (sid, r) in enumerate(sorted_sites, 1):
        conservative = r["rating"].mu - 3 * r["rating"].sigma
        consensus    = round(1 - (r["rating"].sigma / 8.333), 3)
        in_corpus    = (
            r["comparisons"] >= MIN_COMPARISONS
            and conservative >= 10  # TrueSkill conservative threshold
        )

        # Load title
        title = "?"
        meta_path = DATA_DIR / sid / METADATA_FILE
        if meta_path.exists():
            meta  = json.loads(meta_path.read_text())
            title = meta.get("title", sid)[:25]

        table.add_row(
            str(rank),
            sid,
            title,
            f"{conservative:.2f}",
            f"{r['rating'].mu:.2f}",
            f"{r['rating'].sigma:.2f}",
            f"{consensus:.2f}",
            str(r["comparisons"]),
            "✅" if in_corpus else f"{'🔄' if r['comparisons'] < MIN_COMPARISONS else '❌'}",
        )

    console.print(table)
    console.print(
        f"\n[dim]Corpus eligible: "
        f"{sum(1 for _, r in ratings.items() if r['comparisons'] >= MIN_COMPARISONS and r['rating'].mu - 3 * r['rating'].sigma >= 10)} sites[/dim]"
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TASTE Pairwise Validator")
    parser.add_argument("--report", action="store_true", help="Show rankings without running comparisons")
    parser.add_argument("--rounds", type=int, default=20, help="Number of comparison rounds per session")
    args = parser.parse_args()

    if args.report:
        show_rankings()
    else:
        run_comparison_session(max_rounds=args.rounds)
