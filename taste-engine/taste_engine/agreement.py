"""How far voters agree: with each other, with themselves, and across rounds.

Votes are stored exactly as cast. The agreement views in the voting schema line
them up; this module reads those views and summarises them for
``taste votes agreement``.
"""

from __future__ import annotations

from typing import Any

from supabase import Client
from taste_engine import db
from taste_engine.schemas import Round

# Each view, with the columns that give it a stable order for paging.
VIEWS = {
    "pair_agreement": ("round", "pair_low", "pair_high"),
    "voter_consistency": ("round", "voter_id"),
    "voter_effort": ("round", "voter_id"),
    "voter_agreement": ("round", "voter_a_id", "voter_b_id"),
    "round_differences": ("voter_id", "pair_low", "pair_high"),
}


def fetch(client: Client) -> dict[str, list[dict[str, Any]]]:
    return {view: db.select_all(client, view, order) for view, order in VIEWS.items()}


def _share(part: float, whole: float) -> str:
    return f"{part / whole:.0%}" if whole else "n/a"


def summary(views: dict[str, list[dict[str, Any]]]) -> list[str]:
    lines = []
    for round_kind in Round:
        lines.append(f"{round_kind.value.capitalize()} round")
        pairs = [
            p for p in views["pair_agreement"] if p["round"] == round_kind and p["judged"] >= 2
        ]
        if pairs:
            mean = sum(float(p["agreement"]) for p in pairs) / len(pairs)
            split = sum(1 for p in pairs if p["split"])
            lines.append(
                f"  panel: {mean:.0%} mean agreement on {len(pairs)} pairs judged by 2 or more "
                f"voters; split on {split}"
            )
        else:
            lines.append("  panel: no pair judged by 2 or more voters yet")
        for row in views["voter_agreement"]:
            if row["round"] == round_kind:
                lines.append(
                    f"  {row['voter_a']} and {row['voter_b']}: same verdict on "
                    f"{row['same_verdict']} of {row['shared_pairs']} shared pairs "
                    f"({_share(row['same_verdict'], row['shared_pairs'])}), "
                    f"opposite on {row['opposite']}"
                )
        for row in views["voter_effort"]:
            if row["round"] == round_kind:
                lines.append(
                    f"  {row['voter']}: {row['votes']} votes, median {row['median_seconds']} s, "
                    f"{row['fast_votes']} faster than the low-effort limit"
                )
        for row in views["voter_consistency"]:
            if row["round"] == round_kind:
                lines.append(
                    f"  {row['voter']} on repeats: same verdict on {row['same_verdict']} of "
                    f"{row['repeated_pairs']}, flipped on {row['flipped']}"
                )
    differences = views["round_differences"]
    differ = sum(1 for d in differences if d["differs"])
    opposite = sum(1 for d in differences if d["opposite"])
    lines.append(
        f"Visual against motion, same voter and pair: verdict differs on {differ} of "
        f"{len(differences)}, opposite on {opposite}"
        if differences
        else "Visual against motion: no voter has judged a pair in both rounds yet"
    )
    return lines
