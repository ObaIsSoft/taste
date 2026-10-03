"""Pick calibration sites automatically: the most varied set of votable captures.

Every voter judges every calibration pair, so the set should span what the pool holds:
dark and light, type-led and image-led, quiet and loud, still and animated. Every numeric
feature the capture measured takes part (hero pixels and layout for the visual round,
motion metrics for the motion round), each turned into a rank so no outlier dominates.
The pick starts from the most typical site and keeps adding the site least like those
already chosen (farthest-point sampling), so the same captures always give the same set.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from taste_engine import db
from taste_engine.analysis.features import FEATURES_FILE
from taste_engine.capture import store
from taste_engine.describe import DESCRIPTION_FILE
from taste_engine.schemas import Round
from taste_engine.settings import Settings


def _numbers(value: Any, prefix: str = "") -> dict[str, float]:
    """Every numeric leaf of a features section, flattened: no list of chosen features."""
    if isinstance(value, bool):
        return {prefix: float(value)}
    if isinstance(value, int | float):
        return {prefix: float(value)}
    if isinstance(value, dict):
        return {
            k: v
            for key, item in value.items()
            for k, v in _numbers(item, f"{prefix}.{key}").items()
        }
    if isinstance(value, list) and all(isinstance(item, int | float) for item in value):
        return {f"{prefix}[{i}]": float(item) for i, item in enumerate(value)}
    return {}


def _section(features: dict[str, Any], round_kind: Round) -> dict[str, float]:
    if round_kind is Round.MOTION:
        return _numbers(features["motion"], "motion")
    hero = next(p for p in features["pixels"] if p["still"] == 1)
    return {**_numbers(hero, "hero"), **_numbers(features["layout"], "layout")}


def candidates(settings: Settings, round_kind: Round) -> dict[str, dict[str, float]]:
    """Votable captures that suit the round (four screens for visual, a reel for motion)."""
    found = {}
    for directory in sorted(p for p in settings.captures_dir.glob("*-original") if p.is_dir()):
        record = store.read_record(directory)
        described = (
            json.loads((directory / DESCRIPTION_FILE).read_text())
            if (directory / DESCRIPTION_FILE).exists()
            else {}
        )
        if not db.votable(record, described.get("description"), settings):
            continue
        if round_kind is Round.VISUAL and len(record.stills) < settings.capture.screens:
            continue
        if round_kind is Round.MOTION and not record.reel_file:
            continue
        if not (directory / FEATURES_FILE).exists():
            continue
        found[directory.name] = _section(
            json.loads((directory / FEATURES_FILE).read_text()), round_kind
        )
    return found


def pick(vectors: dict[str, dict[str, float]], count: int) -> list[str]:
    """The ``count`` most varied ids: farthest-point sampling over rank-scaled features."""
    ids = sorted(vectors)
    if len(ids) < count:
        raise ValueError(f"only {len(ids)} candidates for {count} calibration sites")
    names = sorted({name for vector in vectors.values() for name in vector})
    table = np.array([[vectors[i].get(name, np.nan) for name in names] for i in ids])
    ranks = np.zeros_like(table)
    for column in range(table.shape[1]):
        values = table[:, column]
        known = ~np.isnan(values)
        if known.sum() < 2 or np.nanmin(values) == np.nanmax(values):
            continue  # a feature nobody varies on says nothing about variety
        order = values[known].argsort().argsort()
        ranks[known, column] = order / (known.sum() - 1)
        ranks[~known, column] = 0.5  # unmeasured: treated as typical
    chosen = [int(np.linalg.norm(ranks - np.median(ranks, axis=0), axis=1).argmin())]
    distance = np.linalg.norm(ranks - ranks[chosen[0]], axis=1)
    while len(chosen) < count:
        nxt = int(distance.argmax())
        chosen.append(nxt)
        distance = np.minimum(distance, np.linalg.norm(ranks - ranks[nxt], axis=1))
    return sorted(ids[i] for i in chosen)
