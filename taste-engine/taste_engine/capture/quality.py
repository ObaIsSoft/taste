"""Quality flags decide whether a capture may enter the voting pool."""

from __future__ import annotations

from urllib.parse import urlsplit

from taste_engine.capture.overlays import cued, same_page, same_site
from taste_engine.schemas import QualityFlags
from taste_engine.settings import CaptureSettings

BLOCKED_STATUSES = frozenset({403, 429})
GONE_STATUSES = frozenset({404, 410})


def assess(
    *,
    cfg: CaptureSettings,
    requested_url: str,
    landed_url: str | None,
    final_url: str | None,
    http_status: int | None,
    title: str | None,
    text_sample: str,
    hero_spread: float | None,
    consent_left: list[str],
    gate_text: str | None,
    clicked: bool,
    reel_expected: bool,
    reel_ok: bool,
) -> QualityFlags:
    text = text_sample.lower()
    heading = (title or "").lower()
    short = len(text) < cfg.short_page_chars
    challenge = any(p in heading for p in cfg.bot_block_patterns) or (
        len(text) < cfg.bot_block_max_chars and any(p in text for p in cfg.bot_block_patterns)
    )
    server_error = http_status is not None and http_status >= 500
    paths = {urlsplit(u).path.rstrip("/") for u in (landed_url, final_url) if u}
    # A page change counts only when our clicks caused it; a site that moves on by itself
    # (an intro that hands over to the home page) is showing its own flow.
    moved_on = (
        clicked
        and final_url is not None
        and landed_url is not None
        and not same_page(final_url, landed_url)
    )
    gate = gate_text is not None and cued(gate_text, cfg.gate_cues)
    notes = [f"consent still visible: {selector}" for selector in consent_left]
    if moved_on:
        notes.append(f"page changed after load: {landed_url} -> {final_url}")
    if gate:
        notes.append(f"gate still blocking: {gate_text}")
    return QualityFlags(
        blank_hero=hero_spread is not None and hero_spread < cfg.blank_std,
        bot_block=http_status in BLOCKED_STATUSES or challenge,
        site_down=server_error and not challenge,
        not_found=http_status in GONE_STATUSES
        or any(p in heading for p in cfg.not_found_patterns)
        or (short and any(p in text for p in cfg.not_found_patterns)),
        parked=bool(paths & set(cfg.parked_paths))
        or any(p in heading or p in text for p in cfg.parked_patterns),
        spam=any(p in heading for p in cfg.spam_patterns)
        or sum(text.count(p) for p in cfg.spam_patterns) >= cfg.spam_min_mentions,
        navigated_away=(final_url is not None and not same_site(final_url, requested_url))
        or moved_on,
        overlay_remaining=bool(consent_left),
        gate_remaining=gate,
        reel_missing=reel_expected and not reel_ok,
        notes=notes,
    )
