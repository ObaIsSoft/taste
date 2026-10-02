"""Browser and context setup, identical for every visit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from taste_engine.settings import CaptureSettings


def launch(playwright: Playwright, cfg: CaptureSettings) -> Browser:
    options: dict[str, Any] = {"headless": cfg.headless, "args": list(cfg.browser_args)}
    if cfg.browser_executable:
        options["executable_path"] = str(cfg.browser_executable)
    return playwright.chromium.launch(**options)


def new_context(
    browser: Browser,
    cfg: CaptureSettings,
    init_scripts: list[str],
    *,
    video_dir: Path | None = None,
    storage_state: dict[str, Any] | None = None,
    reduced_motion: bool = False,
) -> BrowserContext:
    viewport = {"width": cfg.viewport_width, "height": cfg.viewport_height}
    options: dict[str, Any] = {
        "viewport": viewport,
        "locale": cfg.locale,
        "timezone_id": cfg.timezone,
        "device_scale_factor": 1,
    }
    if video_dir is not None:
        options["record_video_dir"] = str(video_dir)
        options["record_video_size"] = viewport
    if storage_state is not None:
        options["storage_state"] = storage_state
    if reduced_motion:
        options["reduced_motion"] = "reduce"
    context = browser.new_context(**options)
    context.set_default_timeout(cfg.click_timeout_s * 1000)
    for script in init_scripts:
        context.add_init_script(script)
    return context


def close_extra_pages(context: BrowserContext, keep: Page) -> None:
    """Close tabs a click opened, so the capture stays on the page under test."""
    for page in context.pages:
        if page is not keep:
            page.close()
