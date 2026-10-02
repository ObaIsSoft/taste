"""Consent banners and intro gates: exact, scoped clicks with a navigation guard.

Text is matched exactly (case-insensitive), never as a substring, so "Enter"
cannot hit "Enterprise". Consent buttons are only looked for inside consent
containers. Gate buttons are only clicked when the page looks gated. Any click
that leaves the site is undone with a back navigation and recorded.
"""

from __future__ import annotations

import logging
import re
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
        box = target.bounding_box()
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


def _pass_gate(page: Page, cfg: CaptureSettings) -> str | None:
    try:
        gated = page.evaluate(js.LOOKS_GATED, cfg.gate_cover_ratio)
    except PlaywrightError:
        return None
    if not gated:
        return None
    for text in cfg.gate_texts:
        pattern = _exact(text)
        for locator in (
            page.get_by_role("button", name=pattern),
            page.get_by_role("link", name=pattern),
            page.get_by_text(pattern),
        ):
            if locator.count() and _click(page, locator, cfg):
                return f"gate:{text}"
    return None


def dismiss_overlays(page: Page, cfg: CaptureSettings, origin: str) -> list[str]:
    """Click through consent banners and intro gates. Returns the actions taken, in order."""
    actions: list[str] = []
    for _ in range(cfg.overlay_rounds):
        action = _accept_consent(page, cfg) or _pass_gate(page, cfg)
        if not action:
            break
        actions.append(action)
        page.wait_for_timeout(cfg.screen_settle_s * 1000)
        close_extra_pages(page.context, keep=page)
        if same_site(page.url, origin):
            continue
        actions.append(f"left-site:{site_host(page.url)}")
        try:
            page.go_back(wait_until="domcontentloaded", timeout=cfg.navigation_timeout_s * 1000)
        except PlaywrightError:
            log.warning("could not return from %s", page.url)
        if not same_site(page.url, origin):
            break
    return actions
