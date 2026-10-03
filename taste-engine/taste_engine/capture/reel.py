"""The UX reel: one scripted visit recorded as video, with the same choreography for every site.

Load and intro play untouched until the page settles, then a slow scroll through
the first screens, a scroll back, hovers on the first links and buttons, and the
menu opened. Consent cookies from the analysis visit are reused, so banners
rarely appear. A click that changes the page is undone, so the reel stays on it.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page
from playwright.sync_api import Error as PlaywrightError

from taste_engine.capture import js, visual
from taste_engine.capture.browser import close_extra_pages, new_context
from taste_engine.capture.overlays import dismiss_overlays, same_page
from taste_engine.settings import CaptureSettings

log = logging.getLogger(__name__)

REEL_FILE = "reel.mp4"  # the voting UI uses the hero still as its poster


@dataclass
class Reel:
    seconds: float | None
    actions: list[str] = field(default_factory=list)


def _scroll(page: Page, distance: float, px_per_s: float, cfg: CaptureSettings) -> None:
    """Chromium's own scroll gesture: real wheel input, in step with the screen's frames, at a set
    speed. Every recorded frame moves, on a plain page as on one with a smooth-scroll library,
    and a page slow to handle input cannot stretch it."""
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send(
            "Input.synthesizeScrollGesture",
            {
                "x": cfg.viewport_width / 2,
                "y": cfg.viewport_height / 2,
                "yDistance": -distance,  # negative moves the content up: scrolling down
                "speed": round(px_per_s),
                "gestureSourceType": "mouse",
            },
        )
    finally:
        cdp.detach()


def _choreograph(page: Page, cfg: CaptureSettings, started: float) -> list[str]:
    reel = cfg.reel
    width, height = cfg.viewport_width, cfg.viewport_height
    visual.wait_until_settled(page, cfg, started, reel.intro_s, reel.intro_max_s)
    landed = page.url
    actions = dismiss_overlays(page, cfg)

    def out_of_time() -> bool:  # a slow page shortens the reel; it never stalls the capture
        if time.monotonic() - started < reel.max_s:
            return False
        actions.append("cut-short")
        return True

    page.mouse.move(width / 2, height / 2)
    for _ in range(reel.screens - 1):
        _scroll(page, height, reel.scroll_px_per_s, cfg)
        page.wait_for_timeout(reel.pause_per_screen_s * 1000)
        if out_of_time():
            return actions
    distance_back = -(reel.screens - 1) * height
    _scroll(page, distance_back, reel.scroll_px_per_s * reel.return_speedup, cfg)
    page.wait_for_timeout(reel.pause_per_screen_s * 1000)

    for point in page.evaluate(js.HOVER_TARGETS, reel.hover_targets):
        if out_of_time():
            return actions
        page.mouse.move(point["x"], point["y"], steps=reel.hover_move_steps)
        page.wait_for_timeout(reel.hover_dwell_s * 1000)

    if out_of_time():
        return actions
    menu = page.evaluate(js.MENU_BUTTON)
    if menu:
        page.mouse.click(menu["x"], menu["y"])
        page.wait_for_timeout(reel.menu_dwell_s * 1000)
        close_extra_pages(page.context, keep=page)
        if same_page(page.url, landed):
            page.keyboard.press("Escape")
            page.wait_for_timeout(reel.hover_dwell_s * 1000)
            actions.append("menu")
        else:
            actions.append(f"menu-left-page:{page.url}")
            page.go_back(wait_until="domcontentloaded", timeout=cfg.navigation_timeout_s * 1000)
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
            started = time.monotonic()
            page.goto(url, wait_until="domcontentloaded", timeout=cfg.navigation_timeout_s * 1000)
            actions = _choreograph(page, cfg, started)
        except PlaywrightError as exc:  # keep the partial reel; the record notes what broke
            log.warning("reel choreography stopped: %s", exc)
            actions.append(f"stopped:{type(exc).__name__}")
        finally:
            video = page.video
            context.close()
        raw = Path(video.path()) if video else None
        if raw is None or not raw.exists():
            return Reel(seconds=None, actions=actions)
        try:
            _transcode(raw, out_dir / REEL_FILE, cfg)
        except (OSError, subprocess.CalledProcessError) as exc:  # keep the stills; flag the reel
            log.warning("reel transcode failed: %s", exc)
            (out_dir / REEL_FILE).unlink(missing_ok=True)
            return Reel(seconds=None, actions=[*actions, "transcode-failed"])
    return Reel(seconds=_duration(out_dir / REEL_FILE, cfg), actions=actions)
