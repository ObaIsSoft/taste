"""Consent banners, gates and pop-ups: exact, scoped clicks with a navigation guard.

Text is matched exactly (case-insensitive, either apostrophe), never as a
substring, so "Enter" cannot hit "Enterprise". Consent buttons are looked for
inside consent containers. Gate answers are looked for inside the layer that
blocks the page: one that covers the screen, offers a few choices and stays on
top when the page scrolls. A smaller floating box (a newsletter offer, a cookie
box without the usual names) is answered by what it says: accept for cookies,
yes for an age question, otherwise "No thanks", "Close" or Escape. Any click
that leaves the page is undone and recorded.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
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


def cued(text: str, cues: list[str]) -> bool:
    """Whether any cue starts a word in the text ("alcol" finds "alcolici")."""
    return any(re.search(rf"\b{re.escape(cue)}", text.lower()) for cue in cues)


def _exact(text: str) -> re.Pattern[str]:
    words = re.escape(text).replace("'", "['’]")  # "J'accepte" also matches "J’accepte"
    return re.compile(rf"^\s*{words}\s*$", re.IGNORECASE)


_CLOSE_LABEL = re.compile(
    r"\b(close|dismiss|fermer|chiudi|cerrar|schlie(ß|ss)en|sluiten|fechar)\b", re.I
)


def _click(page: Page, locator: Locator, cfg: CaptureSettings) -> bool:
    target = locator.first
    try:
        if not target.is_visible():
            return False
        target.click(timeout=cfg.click_timeout_s * 1000)
        return True
    except PlaywrightError:
        pass
    try:  # the click was refused (still moving, say): click its centre like a person would,
        # but only if the centre really is this element, never whatever lies on top of it
        box = target.bounding_box(timeout=cfg.click_timeout_s * 1000)
        if not box:
            return False
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        if not target.evaluate(js.HITS_ELEMENT, [x, y]):
            return False
    except PlaywrightError:
        return False
    page.mouse.click(x, y)
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
    answer = _answer(page, layer, cfg.gate_texts + cfg.dismiss_texts, cfg)
    return f"gate:{answer}" if answer else None


def _answer(page: Page, layer: Locator, texts: list[str], cfg: CaptureSettings) -> str | None:
    for text in texts:
        pattern = _exact(text)
        for locator in (
            layer.get_by_role("button", name=pattern),
            layer.get_by_role("link", name=pattern),
            layer.get_by_text(pattern),
        ):
            if locator.count() and _click(page, locator, cfg):
                return text
    return None


def _gone(page: Page, cfg: CaptureSettings) -> bool:
    page.wait_for_timeout(cfg.settle_poll_s * 1000)
    try:
        return bool(page.evaluate(js.POPUP_GONE))
    except PlaywrightError:
        return True  # the page moved on; the navigation guard deals with it


def _try_popup(page: Page, layer: Locator, text: str, cfg: CaptureSettings) -> str | None:
    if cued(text, cfg.consent_cues):
        texts = cfg.accept_texts
    elif cued(text, cfg.gate_cues):
        texts = cfg.gate_texts + cfg.dismiss_texts
    else:
        texts = cfg.dismiss_texts
    answer = _answer(page, layer, texts, cfg)
    if answer and _gone(page, cfg):
        return f"popup:{answer}"
    close = layer.get_by_role("button", name=_CLOSE_LABEL)  # an icon button labelled "Close"
    if close.count() and _click(page, close, cfg) and _gone(page, cfg):
        return "popup:close"
    page.keyboard.press("Escape")
    return "popup:escape" if _gone(page, cfg) else None


def _close_popup(page: Page, cfg: CaptureSettings) -> str | None:
    """Close the floating box on top of the page. A candidate that does not go away when
    answered was not a pop-up (a site's own panel, say): it is marked and never tried again."""
    for _ in range(cfg.popup_candidates):
        try:
            popup = page.evaluate(js.FIND_POPUP, [cfg.popup_min_area, cfg.popup_max_controls])
        except PlaywrightError:
            return None
        if popup is None:
            return None
        action = _try_popup(page, page.locator("[data-taste-popup]"), popup["text"], cfg)
        if action:
            return action
        try:
            page.evaluate(js.NOT_A_POPUP)
        except PlaywrightError:
            return None
    return None


Step = Callable[[Page, CaptureSettings], "str | None"]


def _run(page: Page, cfg: CaptureSettings, steps: list[Step], settle_s: float) -> list[str]:
    """Run the steps until none acts. A click that opened another page was not a way past an
    overlay: the browser goes back, the step is recorded, and no more clicks are tried."""
    actions: list[str] = []
    landed = page.url
    for _ in range(cfg.overlay_rounds):
        action = next((a for step in steps if (a := step(page, cfg))), None)
        if not action:
            break
        actions.append(action)
        page.wait_for_timeout(settle_s * 1000)
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


def dismiss_overlays(page: Page, cfg: CaptureSettings) -> list[str]:
    """Click through consent banners, gates and pop-ups after the page loads. Returns the
    actions taken, in order."""
    return _run(page, cfg, [_accept_consent, _pass_gate, _close_popup], cfg.screen_settle_s)


def clear_popups(page: Page, cfg: CaptureSettings) -> list[str]:
    """Answer cookie boxes and pop-ups that appeared late, without scrolling: run before each
    still, so a newsletter offer on a timer never covers a screenshot."""
    return _run(page, cfg, [_accept_consent, _close_popup], cfg.settle_poll_s)
