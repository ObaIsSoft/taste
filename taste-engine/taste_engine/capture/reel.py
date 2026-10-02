"""The UX reel: one scripted visit recorded as video, with the same choreography for every site.

Load and intro play untouched, then a slow scroll through the first screens,
a scroll back, hovers on the first links and buttons, and the menu opened.
Consent cookies from the analysis visit are reused, so banners rarely appear.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page
from playwright.sync_api import Error as PlaywrightError

from taste_engine.capture import js
from taste_engine.capture.browser import close_extra_pages, new_context
from taste_engine.capture.overlays import dismiss_overlays, same_site
from taste_engine.settings import CaptureSettings

log = logging.getLogger(__name__)

REEL_FILE = "reel.mp4"
POSTER_FILE = "poster.jpg"


@dataclass
class Reel:
    seconds: float | None
    actions: list[str] = field(default_factory=list)


def _wheel(page: Page, distance: float, px_per_s: float, step_px: int) -> None:
    steps = max(1, int(abs(distance) / step_px))
    delta = step_px if distance > 0 else -step_px
    for _ in range(steps):
        page.mouse.wheel(0, delta)
        page.wait_for_timeout(step_px / px_per_s * 1000)


def _choreograph(page: Page, url: str, cfg: CaptureSettings) -> list[str]:
    reel = cfg.reel
    width, height = cfg.viewport_width, cfg.viewport_height
    page.wait_for_timeout(reel.intro_s * 1000)
    actions = dismiss_overlays(page, cfg, url)

    page.mouse.move(width / 2, height / 2)
    for _ in range(reel.screens - 1):
        _wheel(page, height, reel.scroll_px_per_s, reel.scroll_step_px)
        page.wait_for_timeout(reel.pause_per_screen_s * 1000)
    distance_back = -(reel.screens - 1) * height
    _wheel(page, distance_back, reel.scroll_px_per_s * reel.return_speedup, reel.scroll_step_px)
    page.wait_for_timeout(reel.pause_per_screen_s * 1000)

    for point in page.evaluate(js.HOVER_TARGETS, reel.hover_targets):
        page.mouse.move(point["x"], point["y"], steps=reel.hover_move_steps)
        page.wait_for_timeout(reel.hover_dwell_s * 1000)

    menu = page.evaluate(js.MENU_BUTTON)
    if menu:
        page.mouse.click(menu["x"], menu["y"])
        page.wait_for_timeout(reel.menu_dwell_s * 1000)
        close_extra_pages(page.context, keep=page)
        if same_site(page.url, url):
            page.keyboard.press("Escape")
            page.wait_for_timeout(reel.hover_dwell_s * 1000)
            actions.append("menu")
        else:
            actions.append("menu-left-site")
    return actions


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def _transcode(raw: Path, out: Path, cfg: CaptureSettings) -> None:
    reel = cfg.reel
    _run(
        [
            cfg.ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw),
            "-vf",
            f"scale={reel.output_width}:-2,fps={reel.fps}",
            "-c:v",
            "libx264",
            "-preset",
            reel.preset,
            "-crf",
            str(reel.crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(out),
        ]
    )


def _duration(path: Path, cfg: CaptureSettings) -> float | None:
    result = subprocess.run(
        [
            cfg.ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return round(float(result.stdout.strip()), 2)
    except ValueError:
        return None


def _poster(reel_path: Path, poster_path: Path, at_s: float, cfg: CaptureSettings) -> None:
    _run(
        [
            cfg.ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{at_s:.2f}",
            "-i",
            str(reel_path),
            "-frames:v",
            "1",
            "-q:v",
            str(cfg.reel.poster_qscale),
            str(poster_path),
        ]
    )


def record_reel(
    browser: Browser,
    url: str,
    cfg: CaptureSettings,
    init_scripts: list[str],
    storage_state: dict[str, Any] | None,
    out_dir: Path,
) -> Reel:
    actions: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        context = new_context(
            browser, cfg, init_scripts, video_dir=Path(tmp), storage_state=storage_state
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=cfg.navigation_timeout_s * 1000)
            actions = _choreograph(page, url, cfg)
        except PlaywrightError as exc:  # keep the partial reel; the record notes what broke
            log.warning("reel choreography stopped: %s", exc)
            actions.append(f"stopped:{type(exc).__name__}")
        finally:
            video = page.video
            context.close()
        raw = Path(video.path()) if video else None
        if raw is None or not raw.exists():
            return Reel(seconds=None, actions=actions)
        _transcode(raw, out_dir / REEL_FILE, cfg)
    seconds = _duration(out_dir / REEL_FILE, cfg)
    if seconds:
        _poster(out_dir / REEL_FILE, out_dir / POSTER_FILE, min(cfg.reel.intro_s, seconds / 2), cfg)
    return Reel(seconds=seconds, actions=actions)
