"""Capture one site variant: an analysis visit, a reel visit and a reduced-motion check.

The analysis visit measures the page at scroll 0 before anything moves it:
DOM boxes and design tokens, then the per-screen stills, then a wheel test for
frame drops and scroll hijacking. Nothing is injected that changes the design
(degraded twins excepted, which is the point of them).
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from taste_engine.capture import degrade, js, store, visual
from taste_engine.capture.browser import launch, new_context
from taste_engine.capture.overlays import dismiss_overlays
from taste_engine.capture.quality import assess
from taste_engine.capture.reel import REEL_FILE, Reel, record_reel
from taste_engine.schemas import (
    CaptureRecord,
    CaptureStatus,
    SiteEntry,
    Still,
    UXMetrics,
    Variant,
    capture_id,
)
from taste_engine.settings import CaptureSettings, Settings

log = logging.getLogger(__name__)

DOM_FILE = "dom.json"
TOKENS_FILE = "tokens.json"
ANIMATIONS_FILE = "animations.json"


@dataclass
class Analysis:
    final_url: str | None = None
    http_status: int | None = None
    title: str | None = None
    page_height: int | None = None
    content_visible_ms: float | None = None
    running_animations: int = 0
    overlay_actions: list[str] = field(default_factory=list)
    consent_left: list[str] = field(default_factory=list)
    text_sample: str = ""
    stills: list[Still] = field(default_factory=list)
    hero_spread: float | None = None
    frames: list[float] = field(default_factory=list)
    scroll_hijacked: bool | None = None
    scroll_signals: list[str] = field(default_factory=list)
    animations: list[dict[str, Any]] = field(default_factory=list)
    uses_reduced_motion_query: bool | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    storage_state: dict[str, Any] | None = None


def _ms(seconds: float) -> float:
    return seconds * 1000


def _network_idle(page: Page, cfg: CaptureSettings) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=_ms(cfg.network_idle_timeout_s))
    except PlaywrightTimeout:
        log.debug("network never went idle on %s", page.url)


def _wait_until_settled(page: Page, cfg: CaptureSettings, started: float) -> float | None:
    """Poll the viewport until it shows content and stops changing.

    Returns milliseconds from ``started`` until content first appeared (the
    preloader wait), or None if the page stayed blank.
    """
    visible_ms = None
    previous = None
    while time.monotonic() < started + cfg.settle_max_s:
        thumb = visual.thumbnail(page.screenshot(type="png"))
        elapsed = time.monotonic() - started
        if visible_ms is None and visual.spread(thumb) > cfg.blank_std:
            visible_ms = _ms(elapsed)
        still = previous is not None and visual.difference(previous, thumb) < cfg.stable_diff
        if visible_ms is not None and still and elapsed >= cfg.settle_min_s:
            break
        previous = thumb
        page.wait_for_timeout(_ms(cfg.settle_poll_s))
    return visible_ms


def _scroll_y(page: Page) -> int:
    return int(page.evaluate(js.SCROLL_STATE)["y"])


def _screen_thumb(page: Page):
    return visual.thumbnail(page.screenshot(type="png"))


def _capture_stills(page: Page, cfg: CaptureSettings, out_dir: Path) -> tuple[list[Still], float]:
    width, height = cfg.viewport_width, cfg.viewport_height
    page.evaluate(js.SCROLL_TO, 0)
    page.wait_for_timeout(_ms(cfg.screen_settle_s))
    stills: list[Still] = []
    hero_spread = 0.0
    previous_y = 0
    for index in range(1, cfg.screens + 1):
        method = "top"
        if index > 1:
            before = _screen_thumb(page)
            page.evaluate(js.SCROLL_TO, (index - 1) * height)
            page.wait_for_timeout(_ms(cfg.screen_settle_s))
            method = "native"
            if (
                _scroll_y(page) < previous_y + height / 4
            ):  # native scroll did not reveal new content
                page.mouse.move(width / 2, height / 2)
                page.mouse.wheel(0, height)
                page.wait_for_timeout(_ms(cfg.screen_settle_s))
                method = "wheel"
                if visual.difference(before, _screen_thumb(page)) < cfg.stable_diff:
                    break  # nothing moved: the page has no more screens
        png = page.screenshot(type="png")
        if index == 1:
            hero_spread = visual.spread(visual.thumbnail(png))
        name = f"screen-{index}.jpg"
        visual.save_jpeg(png, out_dir / name, cfg.still_quality)
        previous_y = _scroll_y(page)
        stills.append(Still(index=index, file=name, scroll_y=previous_y, method=method))
    return stills, hero_spread


def _scroll_test(page: Page, cfg: CaptureSettings) -> tuple[list[float], bool | None, list[str]]:
    """Wheel through the page while sampling frames: jank and scroll hijacking in one pass."""
    page.evaluate(js.SCROLL_TO, 0)
    page.wait_for_timeout(_ms(cfg.screen_settle_s))
    before = _screen_thumb(page)
    page.mouse.move(cfg.viewport_width / 2, cfg.viewport_height / 2)
    page.evaluate(js.START_FRAMES)
    steps = max(1, int(_ms(cfg.jank_test_s) / cfg.jank_step_ms))
    for _ in range(steps):
        page.mouse.wheel(0, cfg.jank_wheel_px)
        page.wait_for_timeout(cfg.jank_step_ms)
    frames = page.evaluate(js.STOP_FRAMES)[1:]  # the first interval includes start-up
    moved = visual.difference(before, _screen_thumb(page)) >= cfg.stable_diff
    native = _scroll_y(page) >= steps * cfg.jank_wheel_px * cfg.native_scroll_share
    page.evaluate(js.SCROLL_TO, 0)
    if native:
        return frames, False, []
    if moved:
        return frames, True, ["content moves without native scrolling"]
    return frames, None, ["page did not scroll"]


def _merge_animations(*snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for snapshot in snapshots:
        for item in snapshot:
            merged.setdefault((item["kind"], item["name"], item["target"]), item)
    return list(merged.values())


def _analysis_visit(
    browser: Browser, url: str, cfg: CaptureSettings, scripts: list[str], out_dir: Path
) -> Analysis:
    result = Analysis()
    context = new_context(browser, cfg, scripts)
    try:
        page = context.new_page()
        started = time.monotonic()
        response = page.goto(
            url, wait_until="domcontentloaded", timeout=_ms(cfg.navigation_timeout_s)
        )
        result.http_status = response.status if response else None
        result.content_visible_ms = _wait_until_settled(page, cfg, started)  # the preloader wait
        _network_idle(page, cfg)
        _wait_until_settled(page, cfg, time.monotonic())  # late content can still arrive
        result.running_animations = page.evaluate(js.RUNNING_ANIMATIONS)
        early_animations = page.evaluate(js.ANIMATIONS, cfg.max_animations)

        result.overlay_actions = dismiss_overlays(page, cfg, url)
        if result.overlay_actions:
            _wait_until_settled(page, cfg, time.monotonic())

        page.evaluate(js.SCROLL_TO, 0)
        dom = page.evaluate(js.EXTRACT_DOM, cfg.max_dom_elements)
        store.write_json(
            out_dir / DOM_FILE, {k: dom[k] for k in ("viewport", "page_height", "elements")}
        )
        store.write_json(out_dir / TOKENS_FILE, dom["tokens"])
        result.title, result.page_height = dom["title"], dom["page_height"]
        result.consent_left = page.evaluate(
            js.CONSENT_VISIBLE, [cfg.consent_scopes, cfg.overlay_cover_ratio]
        )
        result.text_sample = page.evaluate(js.TEXT_SAMPLE, cfg.text_sample_chars)

        result.stills, result.hero_spread = _capture_stills(page, cfg, out_dir)
        result.frames, result.scroll_hijacked, result.scroll_signals = _scroll_test(page, cfg)
        result.animations = _merge_animations(
            early_animations, page.evaluate(js.ANIMATIONS, cfg.max_animations)
        )
        result.uses_reduced_motion_query = page.evaluate(js.REDUCED_MOTION_QUERY)
        result.signals = page.evaluate(js.PAGE_SIGNALS)
        result.final_url = page.url
        result.storage_state = context.storage_state()
    finally:
        context.close()
    return result


def _reduced_motion_running(
    browser: Browser, url: str, cfg: CaptureSettings, scripts: list[str]
) -> int:
    context = new_context(browser, cfg, scripts, reduced_motion=True)
    try:
        page = context.new_page()
        started = time.monotonic()
        page.goto(url, wait_until="domcontentloaded", timeout=_ms(cfg.navigation_timeout_s))
        _network_idle(page, cfg)
        _wait_until_settled(page, cfg, started)
        return page.evaluate(js.RUNNING_ANIMATIONS)
    finally:
        context.close()


def _rounded(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _metrics(analysis: Analysis, reduced_running: int | None, cfg: CaptureSettings) -> UXMetrics:
    perf = analysis.signals.get("perf", {})
    frames = analysis.frames
    dropped_after = cfg.frame_budget_ms * cfg.dropped_frame_factor
    respected = None
    if reduced_running is not None and analysis.running_animations:
        respected = reduced_running < analysis.running_animations
    return UXMetrics(
        content_visible_ms=_rounded(analysis.content_visible_ms),
        first_contentful_paint_ms=_rounded(perf.get("fcp")),
        largest_contentful_paint_ms=_rounded(perf.get("lcp")),
        cumulative_layout_shift=_rounded(perf.get("cls"), 4),
        long_task_count=perf.get("long_tasks"),
        long_task_ms=_rounded(perf.get("long_task_ms")),
        mean_frame_ms=_rounded(statistics.fmean(frames), 2) if frames else None,
        dropped_frame_ratio=round(sum(f > dropped_after for f in frames) / len(frames), 3)
        if frames
        else None,
        inline_motion_mutations=analysis.signals.get("style_mutations"),
        scroll_hijacked=analysis.scroll_hijacked,
        scroll_signals=analysis.scroll_signals,
        reduced_motion_respected=respected,
        uses_reduced_motion_query=analysis.uses_reduced_motion_query,
        transfer_bytes=analysis.signals.get("transfer_bytes"),
        request_count=analysis.signals.get("request_count"),
    )


def capture_site(entry: SiteEntry, variant: Variant, settings: Settings) -> CaptureRecord:
    """Capture one site variant into its own folder and write capture.json, even on failure."""
    cfg = settings.capture
    cid = capture_id(entry.id, variant)
    out_dir = settings.capture_dir(cid)
    store.reset_directory(out_dir)
    url = str(entry.url)
    started = time.monotonic()
    base: dict[str, Any] = {
        "capture_id": cid,
        "site_id": entry.id,
        "variant": variant,
        "requested_url": url,
        "capture_version": settings.capture_version,
        "captured_at": datetime.now(UTC),
        "viewport_width": cfg.viewport_width,
        "viewport_height": cfg.viewport_height,
    }
    scripts = [js.init_script(cfg.max_gsap_calls, cfg.gsap_poll_s)]
    twin = degrade.init_script(variant)
    if twin:
        scripts.append(twin)

    try:
        with sync_playwright() as playwright:
            browser = launch(playwright, cfg)
            try:
                analysis = _analysis_visit(browser, url, cfg, scripts, out_dir)
                reel: Reel | None = None
                if cfg.reel.enabled:
                    reel = record_reel(browser, url, cfg, scripts, analysis.storage_state, out_dir)
                reduced = (
                    _reduced_motion_running(browser, url, cfg, scripts)
                    if cfg.reduced_motion_check
                    else None
                )
            finally:
                browser.close()
    except Exception as exc:  # any failure is recorded, never swallowed: the runner retries it
        log.exception("capture %s failed", cid)
        record = CaptureRecord(
            **base,
            status=CaptureStatus.FAILED,
            error=f"{type(exc).__name__}: {exc}"[:500],
            duration_s=round(time.monotonic() - started, 1),
        )
        store.write_record(record, out_dir)
        return record

    gsap_calls = analysis.signals.get("gsap_calls", [])
    libraries = analysis.signals.get("libraries", {})
    store.write_json(
        out_dir / ANIMATIONS_FILE,
        {"animations": analysis.animations, "gsap_calls": gsap_calls, "libraries": libraries},
    )
    reel_ok = bool(reel and reel.seconds and reel.seconds >= cfg.reel.intro_s)
    record = CaptureRecord(
        **base,
        status=CaptureStatus.OK,
        final_url=analysis.final_url,
        http_status=analysis.http_status,
        title=analysis.title,
        duration_s=round(time.monotonic() - started, 1),
        page_height=analysis.page_height,
        stills=analysis.stills,
        reel_file=REEL_FILE if reel_ok else None,
        reel_seconds=reel.seconds if reel else None,
        overlay_actions=analysis.overlay_actions + (reel.actions if reel else []),
        libraries=libraries,
        animation_count=len(analysis.animations),
        gsap_call_count=len(gsap_calls),
        metrics=_metrics(analysis, reduced, cfg),
        quality=assess(
            cfg=cfg,
            requested_url=url,
            final_url=analysis.final_url,
            http_status=analysis.http_status,
            title=analysis.title,
            text_sample=analysis.text_sample,
            hero_spread=analysis.hero_spread,
            consent_left=analysis.consent_left,
            reel_ok=reel_ok,
        ),
    )
    store.write_record(record, out_dir)
    return record
