"""Capture one site variant: an analysis visit; for originals, a reel and a reduced-motion check.

The analysis visit measures the page at scroll 0 before anything moves it:
DOM boxes and design tokens, then the per-screen stills, then a wheel test for
frame drops and scroll hijacking. Nothing is injected that changes the design
(degraded twins excepted, which is the point of them). Twins only need stills,
so they skip the reel and the reduced-motion visit.
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
from taste_engine.capture.overlays import dismiss_overlays, find_gate
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
    landed_url: str | None = None  # after load and redirects, before anything was clicked
    final_url: str | None = None
    http_status: int | None = None
    title: str | None = None
    page_height: int | None = None
    content_visible_ms: float | None = None
    running_animations: int = 0
    idle_motion: int | None = None  # JavaScript style changes while nobody touches the page
    gate_text: str | None = None  # a gate still blocking the page after the clicks
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


def _settle(page: Page, cfg: CaptureSettings, started: float) -> float | None:
    return visual.wait_until_settled(page, cfg, started, cfg.settle_min_s, cfg.settle_max_s)


def _scroll_y(page: Page) -> int:
    return int(page.evaluate(js.SCROLL_STATE)["y"])


def _next_screen(page: Page, cfg: CaptureSettings, target_y: int) -> tuple[str, int] | None:
    """Bring the next screen into view, the way the page allows. Returns how, and the new
    scroll position, or None when the page has no more screens."""
    height = cfg.viewport_height
    before = visual.screen(page)
    previous = page.evaluate(js.SCROLL_STATE)
    page.evaluate(js.SCROLL_TO, target_y)
    page.wait_for_timeout(_ms(cfg.screen_settle_s))
    y = _scroll_y(page)
    if y >= previous["y"] + height / 4:
        return "native", y
    if previous["y"] > 0:
        return None  # the page scrolls natively and has reached its end
    inner = page.evaluate(js.SCROLL_INNER, height)
    if inner and inner["moved"] >= cfg.inner_scroll_min_px:
        page.wait_for_timeout(_ms(cfg.screen_settle_s))
        return "inner", int(inner["top"])
    # Only the wheel moves this page: a scroll-hijacking library or a slideshow. What the
    # page does on its own (animation) must not count as a new screen.
    idle = visual.difference(before, visual.screen(page))
    page.mouse.move(cfg.viewport_width / 2, height / 2)
    for _ in range(cfg.wheel_attempts):
        for _ in range(5):  # a hand's scroll gesture, not one jump
            page.mouse.wheel(0, height / 5)
            page.wait_for_timeout(60)
        if visual.wait_for_change(page, cfg, before, idle + cfg.stable_diff):
            return "wheel", _scroll_y(page)
    return None


def _capture_stills(page: Page, cfg: CaptureSettings, out_dir: Path) -> tuple[list[Still], float]:
    page.evaluate(js.SCROLL_TO, 0)
    page.evaluate(js.SCROLL_INNER, -cfg.viewport_height * 100)
    page.wait_for_timeout(_ms(cfg.screen_settle_s))
    stills: list[Still] = []
    hero_spread = 0.0
    method, y = "top", 0
    for index in range(1, cfg.screens + 1):
        if index > 1:
            moved = _next_screen(page, cfg, (index - 1) * cfg.viewport_height)
            if moved is None:
                break
            method, y = moved
        png = page.screenshot(type="png")
        if index == 1:
            hero_spread = visual.spread(visual.thumbnail(png))
        name = f"screen-{index}.jpg"
        visual.save_jpeg(png, out_dir / name, cfg.still_quality)
        stills.append(Still(index=index, file=name, scroll_y=y, method=method))
    return stills, hero_spread


def _scroll_test(page: Page, cfg: CaptureSettings) -> tuple[list[float], bool | None, list[str]]:
    """Wheel through the page while sampling frames: jank and scroll hijacking in one pass."""
    page.evaluate(js.SCROLL_TO, 0)
    page.wait_for_timeout(_ms(cfg.screen_settle_s))
    before = visual.screen(page)
    page.mouse.move(cfg.viewport_width / 2, cfg.viewport_height / 2)
    page.evaluate(js.START_FRAMES)
    steps = max(1, int(_ms(cfg.jank_test_s) / cfg.jank_step_ms))
    for _ in range(steps):
        page.mouse.wheel(0, cfg.jank_wheel_px)
        page.wait_for_timeout(cfg.jank_step_ms)
    frames = page.evaluate(js.STOP_FRAMES)[1:]  # the first interval includes start-up
    moved = visual.difference(before, visual.screen(page)) >= cfg.stable_diff
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
        result.content_visible_ms = _settle(page, cfg, started)  # the preloader wait
        _network_idle(page, cfg)
        _settle(page, cfg, time.monotonic())  # late content can still arrive
        result.running_animations = page.evaluate(js.RUNNING_ANIMATIONS)
        result.idle_motion = page.evaluate(js.IDLE_MOTION, _ms(cfg.idle_motion_s))
        early_animations = page.evaluate(js.ANIMATIONS, cfg.max_animations)

        result.landed_url = page.url
        result.overlay_actions = dismiss_overlays(page, cfg)
        if result.overlay_actions:
            _settle(page, cfg, time.monotonic())
        gate = find_gate(page, cfg)
        result.gate_text = gate["text"] if gate else None

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


def _reduced_motion(
    browser: Browser, url: str, cfg: CaptureSettings, scripts: list[str]
) -> tuple[int, int | None]:
    """Running CSS animations and idle JavaScript motion when the visitor asks for less motion."""
    context = new_context(browser, cfg, scripts, reduced_motion=True)
    try:
        page = context.new_page()
        started = time.monotonic()
        page.goto(url, wait_until="domcontentloaded", timeout=_ms(cfg.navigation_timeout_s))
        _network_idle(page, cfg)
        _settle(page, cfg, started)
        running = page.evaluate(js.RUNNING_ANIMATIONS)
        return running, page.evaluate(js.IDLE_MOTION, _ms(cfg.idle_motion_s))
    finally:
        context.close()


def _respects_reduced_motion(
    analysis: Analysis, reduced: tuple[int, int | None] | None, cfg: CaptureSettings
) -> bool | None:
    """True when every kind of motion the page shows (CSS, JavaScript) drops when asked to;
    None when there was no motion to judge or no check ran."""
    if reduced is None:
        return None
    reduced_css, reduced_js = reduced
    checks = []
    if analysis.running_animations:
        checks.append(reduced_css < analysis.running_animations)
    if analysis.idle_motion is not None and analysis.idle_motion >= cfg.idle_motion_min:
        checks.append(reduced_js is not None and reduced_js <= analysis.idle_motion / 2)
    return all(checks) if checks else None


def _rounded(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _metrics(
    analysis: Analysis, reduced: tuple[int, int | None] | None, cfg: CaptureSettings
) -> UXMetrics:
    perf = analysis.signals.get("perf", {})
    frames = analysis.frames
    dropped_after = cfg.frame_budget_ms * cfg.dropped_frame_factor
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
        idle_motion_mutations=analysis.idle_motion,
        scroll_hijacked=analysis.scroll_hijacked,
        scroll_signals=analysis.scroll_signals,
        reduced_motion_respected=_respects_reduced_motion(analysis, reduced, cfg),
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

    motion = variant is Variant.ORIGINAL  # twins differ in static design only
    reel_expected = cfg.reel.enabled and motion
    try:
        with sync_playwright() as playwright:
            browser = launch(playwright, cfg)
            try:
                analysis = _analysis_visit(browser, url, cfg, scripts, out_dir)
                reel: Reel | None = None
                if reel_expected:
                    reel = record_reel(browser, url, cfg, scripts, analysis.storage_state, out_dir)
                reduced = (
                    _reduced_motion(browser, url, cfg, scripts)
                    if cfg.reduced_motion_check and motion
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
            landed_url=analysis.landed_url,
            final_url=analysis.final_url,
            http_status=analysis.http_status,
            title=analysis.title,
            text_sample=analysis.text_sample,
            hero_spread=analysis.hero_spread,
            consent_left=analysis.consent_left,
            gate_text=analysis.gate_text,
            reel_expected=reel_expected,
            reel_ok=reel_ok,
        ),
    )
    store.write_record(record, out_dir)
    return record
