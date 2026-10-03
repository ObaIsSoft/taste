"""Image helpers used to decide when a page is visible and when it has stopped moving."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import Page

from taste_engine.settings import CaptureSettings

_THUMB = (240, 150)  # comparison resolution: enough to see a page change, cheap to diff


def thumbnail(png: bytes) -> Image.Image:
    """In colour: a change from green to an equally bright purple is still a change."""
    with Image.open(BytesIO(png)) as image:
        return image.convert("RGB").resize(_THUMB)


def spread(thumb: Image.Image) -> float:
    """Mean per-channel standard deviation; near zero for a blank frame."""
    stddev = ImageStat.Stat(thumb).stddev
    return sum(stddev) / len(stddev)


def difference(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute per-channel difference between two thumbnails."""
    mean = ImageStat.Stat(ImageChops.difference(a, b)).mean
    return sum(mean) / len(mean)


def save_jpeg(png: bytes, path: Path, quality: int) -> None:
    with Image.open(BytesIO(png)) as image:
        image.convert("RGB").save(path, "JPEG", quality=quality, optimize=True)


def screen(page: Page) -> Image.Image:
    return thumbnail(page.screenshot(type="png"))


def wait_until_settled(
    page: Page, cfg: CaptureSettings, started: float, min_s: float, max_s: float
) -> float | None:
    """Poll the viewport until it shows content and stops changing, for min_s to max_s.

    Returns milliseconds from ``started`` until content first appeared (the
    preloader wait), or None if the page stayed blank.
    """
    visible_ms = None
    previous = None
    while time.monotonic() < started + max_s:
        thumb = screen(page)
        elapsed = time.monotonic() - started
        if visible_ms is None and spread(thumb) > cfg.blank_std:
            visible_ms = elapsed * 1000
        still = previous is not None and difference(previous, thumb) < cfg.stable_diff
        if visible_ms is not None and still and elapsed >= min_s:
            break
        previous = thumb
        page.wait_for_timeout(cfg.settle_poll_s * 1000)
    return visible_ms


def wait_for_change(
    page: Page, cfg: CaptureSettings, before: Image.Image, threshold: float
) -> bool:
    """Whether the screen moves more than ``threshold`` away from ``before`` within
    wheel_wait_s; if it does, wait for the movement to finish."""
    deadline = time.monotonic() + cfg.wheel_wait_s
    while time.monotonic() < deadline:
        page.wait_for_timeout(cfg.settle_poll_s * 1000)
        if difference(before, screen(page)) > threshold:
            wait_until_settled(page, cfg, time.monotonic(), 0, cfg.wheel_wait_s)
            return True
    return False
