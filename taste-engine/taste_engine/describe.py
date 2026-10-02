"""Factual descriptions of hero stills by Claude (the "eyes"), through the Batch API.

The model reports what is visible, never a verdict: the schema has no field for
quality, and nearly every answer comes from a fixed list, so the output is
always valid JSON. A capture whose request fails gets no description.json and
is retried on the next run.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anthropic
from PIL import Image

from taste_engine import batches
from taste_engine.capture import store
from taste_engine.schemas import CaptureStatus
from taste_engine.settings import ClaudeSettings, Settings

log = logging.getLogger(__name__)

JOB = "describe"
DESCRIPTION_FILE = "description.json"

SYSTEM_PROMPT = (
    "You describe website screenshots for a research dataset. Report only what is visible in "
    "the image. Never judge quality, taste or effectiveness, and never use evaluative words such "
    "as clean, modern, premium, elegant or engaging."
)
USER_PROMPT = "This is the first screen of a website. Fill in every field from what is visible."


def _choice(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "focal_subject": _choice(
            "product_interface",
            "people",
            "objects",
            "place",
            "illustration",
            "3d_render",
            "typography_only",
            "video_still",
            "abstract_graphic",
            "none",
        ),
        "background": _choice(
            "flat_light",
            "flat_dark",
            "gradient",
            "photograph",
            "video_still",
            "illustration",
            "texture_or_grain",
            "mixed",
        ),
        "headline_style": _choice("serif", "sans_serif", "display", "monospace", "script", "none"),
        "headline_size": _choice("none", "small", "medium", "large", "oversized"),
        "layout_pattern": _choice(
            "centered_hero",
            "split_text_media",
            "full_bleed_media",
            "grid_of_cards",
            "editorial_columns",
            "asymmetric",
            "list",
            "other",
        ),
        "density": _choice("sparse", "balanced", "dense"),
        "visible_elements": {
            "type": "array",
            "items": _choice(
                "navigation_bar",
                "menu_button",
                "logo",
                "primary_button",
                "secondary_button",
                "logo_strip",
                "badge_or_award",
                "form_field",
                "carousel_controls",
                "cookie_banner",
                "chat_widget",
                "scroll_cue",
                "video_player",
            ),
        },
        "text_over_image": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": [
        "focal_subject",
        "background",
        "headline_style",
        "headline_size",
        "layout_pattern",
        "density",
        "visible_elements",
        "text_over_image",
        "notes",
    ],
    "additionalProperties": False,
}


def _image_block(path: Path, cfg: ClaudeSettings) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
    if rgb.width > cfg.image_max_width:
        height = round(rgb.height * cfg.image_max_width / rgb.width)
        rgb = rgb.resize((cfg.image_max_width, height))
    buffer = io.BytesIO()
    rgb.save(buffer, "JPEG", quality=cfg.image_quality)
    data = base64.standard_b64encode(buffer.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def build_request(capture_id: str, hero: Path, cfg: ClaudeSettings) -> dict[str, Any]:
    return {
        "custom_id": capture_id,
        "params": {
            "model": cfg.describe_model,
            "max_tokens": cfg.describe_max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": [_image_block(hero, cfg), {"type": "text", "text": USER_PROMPT}],
                }
            ],
            "output_config": {
                "effort": cfg.describe_effort,
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
        },
    }


def pending_captures(settings: Settings, capture_ids: list[str] | None, force: bool) -> list[Path]:
    """Successful captures that passed QA and have no description yet."""
    chosen = []
    for directory in sorted(p for p in settings.captures_dir.glob("*") if p.is_dir()):
        if capture_ids is not None and directory.name not in capture_ids:
            continue
        record = store.read_record(directory)
        if record is None or record.status != CaptureStatus.OK or not record.quality.passed:
            continue
        if force or not (directory / DESCRIPTION_FILE).exists():
            chosen.append(directory)
    return chosen


def parse_result(result: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return (description, None) on success, or (None, reason) when it should be retried."""
    text, reason = batches.text_of(result)
    return (json.loads(text), None) if text is not None else (None, reason)


def submit(
    settings: Settings,
    client: anthropic.Anthropic,
    capture_ids: list[str] | None = None,
    force: bool = False,
) -> list[str]:
    requests = [
        build_request(d.name, d / store.read_record(d).stills[0].file, settings.claude)
        for d in pending_captures(settings, capture_ids, force)
    ]
    return batches.submit(settings, client, JOB, requests)


def collect(settings: Settings, client: anthropic.Anthropic, wait: bool = True) -> dict[str, int]:
    """Write description.json for every finished request. Returns counts by outcome."""
    counts = {"described": 0, "retry_later": 0}
    for batch_id, result in batches.collect(settings, client, JOB, wait):
        description, reason = parse_result(result)
        if description is None:
            counts["retry_later"] += 1
            log.warning("%s not described: %s", result.custom_id, reason)
            continue
        store.write_json(
            settings.capture_dir(result.custom_id) / DESCRIPTION_FILE,
            {
                "model": result.result.message.model,
                "batch_id": batch_id,
                "described_at": datetime.now(UTC).isoformat(),
                "description": description,
            },
        )
        counts["described"] += 1
    return counts
