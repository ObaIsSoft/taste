"""Quality flags decide whether a capture may enter the voting pool."""

from __future__ import annotations

from taste_engine.capture.overlays import same_site
from taste_engine.schemas import QualityFlags
from taste_engine.settings import CaptureSettings

BLOCKED_STATUSES = frozenset({403, 429, 503})
GONE_STATUSES = frozenset({404, 410})


def assess(
    *,
    cfg: CaptureSettings,
    requested_url: str,
    final_url: str | None,
    http_status: int | None,
    title: str | None,
    text_sample: str,
    hero_spread: float | None,
    consent_left: list[str],
    reel_ok: bool,
) -> QualityFlags:
    text = text_sample.lower()
    heading = (title or "").lower()
    short = len(text) < cfg.short_page_chars
    return QualityFlags(
        blank_hero=hero_spread is not None and hero_spread < cfg.blank_std,
        bot_block=http_status in BLOCKED_STATUSES
        or (short and any(p in text for p in cfg.bot_block_patterns)),
        not_found=http_status in GONE_STATUSES
        or any(p in heading for p in cfg.not_found_patterns)
        or (short and any(p in text for p in cfg.not_found_patterns)),
        navigated_away=final_url is not None and not same_site(final_url, requested_url),
        overlay_remaining=bool(consent_left),
        reel_missing=cfg.reel.enabled and not reel_ok,
        notes=[f"consent still visible: {selector}" for selector in consent_left],
    )
