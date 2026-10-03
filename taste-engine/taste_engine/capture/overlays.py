"""Consent banners and intro, age and warning gates: exact, scoped clicks with a navigation guard.

Text is matched exactly (case-insensitive), never as a substring, so "Enter"
cannot hit "Enterprise". Consent buttons are only looked for inside consent
containers. Gate answers are only looked for inside the layer that blocks the
page: one that covers most of the screen, offers a few choices and stays on top
when the page scrolls. Any click that leaves the page is undone and recorded.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

from taste_engine.capture import js
from taste_engine.capture.browser import close_extra_pages
from taste_engine.settings import CaptureSettings

log = logging.getLogger(__name__)
_CONSENT_FRAME = re.compile(
    r"consent|cmp|cookie|privacy|sourcepoint|didomi|onetrust|usercentrics", re.IGNORECASE
)


def site_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def same_site(url: str, origin: str) -> bool:
    a, b = site_host(url), site_host(origin)
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def same_page(url: str, other: str) -> bool:
    return same_site(url, other) and urlsplit(url).path.rstrip("/") == urlsplit(other).path.rstrip(
        "/"
    )


def _exact(text: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{re.escape(text)}\s*$", re.IGNORECASE)


def _click(page: Page, locator: Locator, cfg: CaptureSettings) -> bool:
    target = locator.first
    try:
        if not target.is_visible():
            return False
        target.click(timeout=cfg.click_timeout_s * 1000)
        return True
    except PlaywrightError:
        pass
    try:  # something covers the element: click its centre like a person would
        box = target.bounding_box(timeout=cfg.click_timeout_s * 1000)
    except PlaywrightError:
        return False
    if not box:
        return False
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    return True


def _accept_consent(page: Page, cfg: CaptureSettings) -> str | None:
    scopes = page.locator(", ".join(cfg.consent_scopes))
    roots: list[Locator] = [scopes] if scopes.count() else []
    roots += [f.locator("body") for f in page.frames[1:] if _CONSENT_FRAME.search(f.url)]
    for root in roots:
        for text in cfg.accept_texts:
            pattern = _exact(text)
            for locator in (
                root.get_by_role("button", name=pattern),
                root.get_by_role("link", name=pattern),
            ):
                if locator.count() and _click(page, locator, cfg):
                    return f"consent:{text}"
    return None


def find_gate(page: Page, cfg: CaptureSettings) -> dict[str, Any] | None:
    """The layer blocking the page, if any, marked with data-taste-gate. A backdrop that the
    page scrolls over is not a gate, so the page is scrolled one screen to check."""
    args = [cfg.gate_cover_ratio, cfg.gate_max_controls, cfg.gate_max_chars]
    try:
        layer = page.evaluate(js.BLOCKING_OVERLAY, args)
        if layer is None:
            return None
        y = page.evaluate(js.SCROLL_STATE)["y"]
        page.evaluate(js.SCROLL_TO, y + cfg.viewport_height)
        page.wait_for_timeout(cfg.settle_poll_s * 1000)
        still_on_top = page.evaluate(js.BLOCKING_OVERLAY, args)
        page.evaluate(js.SCROLL_TO, y)
    except PlaywrightError:
        return None
    return still_on_top


def _pass_gate(page: Page, cfg: CaptureSettings) -> str | None:
    if find_gate(page, cfg) is None:
        return None
    layer = page.locator("[data-taste-gate]")
    for text in cfg.gate_texts:
        pattern = _exact(text)
        for locator in (
            layer.get_by_role("button", name=pattern),
            layer.get_by_role("link", name=pattern),
            layer.get_by_text(pattern),
        ):
            if locator.count() and _click(page, locator, cfg):
                return f"gate:{text}"
    return None


def dismiss_overlays(page: Page, cfg: CaptureSettings) -> list[str]:
    """Click through consent banners and gates. Returns the actions taken, in order.

    A click that opened another page was not a way past an overlay: the browser goes
    back, the step is recorded, and no more clicks are tried.
    """
    actions: list[str] = []
    landed = page.url
    for _ in range(cfg.overlay_rounds):
        action = _accept_consent(page, cfg) or _pass_gate(page, cfg)
        if not action:
            break
        actions.append(action)
        page.wait_for_timeout(cfg.screen_settle_s * 1000)
        close_extra_pages(page.context, keep=page)
        if same_page(page.url, landed):
            continue
        actions.append(f"left-page:{page.url}")
        try:
            page.go_back(wait_until="domcontentloaded", timeout=cfg.navigation_timeout_s * 1000)
        except PlaywrightError:
            log.warning("could not return from %s", page.url)
        break
    return actions
