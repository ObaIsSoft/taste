"""Compute features.json for each successful capture."""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from taste_engine.analysis.layout import layout_features
from taste_engine.analysis.pixels import pixel_features
from taste_engine.capture import store
from taste_engine.capture.site import ANIMATIONS_FILE, DOM_FILE, TOKENS_FILE
from taste_engine.schemas import CaptureRecord, CaptureStatus
from taste_engine.settings import Settings

log = logging.getLogger(__name__)

FEATURES_FILE = "features.json"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def motion_features(record: CaptureRecord, animations: dict[str, Any]) -> dict[str, object]:
    items = animations.get("animations", [])
    durations = [a["duration_ms"] for a in items if a.get("duration_ms")]
    metrics = record.metrics
    return {
        "animation_count": len(items),
        "animation_kinds": dict(Counter(a["kind"] for a in items)),
        "median_duration_ms": statistics.median(durations) if durations else None,
        "distinct_easings": len({a["easing"] for a in items if a.get("easing")}),
        "infinite_animations": sum(1 for a in items if a.get("iterations") == -1),
        "gsap_calls": record.gsap_call_count,
        "libraries": [name for name, used in record.libraries.items() if used],
        "inline_motion_mutations": metrics.inline_motion_mutations,
        "content_visible_ms": metrics.content_visible_ms,
        "largest_contentful_paint_ms": metrics.largest_contentful_paint_ms,
        "cumulative_layout_shift": metrics.cumulative_layout_shift,
        "dropped_frame_ratio": metrics.dropped_frame_ratio,
        "scroll_hijacked": metrics.scroll_hijacked,
        "reduced_motion_respected": metrics.reduced_motion_respected,
        "transfer_bytes": metrics.transfer_bytes,
    }


def analyse_capture(directory: Path, settings: Settings) -> dict[str, Any]:
    record = store.read_record(directory)
    if record is None or record.status != CaptureStatus.OK:
        raise ValueError(f"{directory.name} has no successful capture")
    features = {
        "analysis_version": settings.analysis_version,
        "capture_id": record.capture_id,
        "pixels": [
            {"still": s.index, **pixel_features(directory / s.file, settings.analysis)}
            for s in record.stills
        ],
        "layout": layout_features(
            _read(directory / DOM_FILE), _read(directory / TOKENS_FILE), settings.analysis
        ),
        "motion": motion_features(record, _read(directory / ANIMATIONS_FILE)),
    }
    store.write_json(directory / FEATURES_FILE, features)
    return features


def analyse_all(
    settings: Settings, capture_ids: list[str] | None = None, force: bool = False
) -> int:
    """Analyse every successful capture that has no current features.json. Returns the count."""
    done = 0
    directories = sorted(p for p in settings.captures_dir.glob("*") if p.is_dir())
    for directory in directories:
        if capture_ids is not None and directory.name not in capture_ids:
            continue
        record = store.read_record(directory)
        if record is None or record.status != CaptureStatus.OK:
            continue
        existing = directory / FEATURES_FILE
        if (
            not force
            and existing.exists()
            and _read(existing).get("analysis_version") == settings.analysis_version
        ):
            continue
        analyse_capture(directory, settings)
        done += 1
        log.info("analysed %s", directory.name)
    return done
