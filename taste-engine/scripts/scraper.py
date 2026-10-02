"""
scraper.py — Step 1: Capture screenshot, full-page video, motion code, and metadata.

What this does differently from the original plan:
  - Records a 30-second interaction video (scroll + hover) via Playwright
  - Extracts actual GSAP timeline calls and CSS animation declarations from live JS
  - Detects motion libraries (GSAP, Framer Motion, Lottie, Three.js, ScrollTrigger)
  - Captures above-fold + full-page screenshots separately
"""
import sys
import json
import os
import time
import base64
import glob
from pathlib import Path

# Allow running from scripts/ or from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from PIL import Image
from rich.console import Console
from config import DATA_DIR, VIEWPORT, SCROLL_SPEED, SCROLL_PAUSE, SCROLL_DURATION, METADATA_FILE, MOTION_CODE_FILE

console = Console()


# ── Motion library fingerprints ────────────────────────────────────────────

MOTION_FINGERPRINTS = """() => {
    const detected = {};
    detected.gsap          = typeof gsap !== 'undefined';
    detected.framerMotion  = !!document.querySelector('[data-framer-component-type]') ||
                             typeof MotionValue !== 'undefined';
    detected.lottie        = typeof lottie !== 'undefined' || typeof LottiePlayer !== 'undefined';
    detected.threeJs       = typeof THREE !== 'undefined';
    detected.scrollTrigger = typeof ScrollTrigger !== 'undefined';
    detected.anime         = typeof anime !== 'undefined';
    detected.velocity      = typeof Velocity !== 'undefined';
    detected.css_has_animation = document.querySelectorAll('[style*=\"animation\"]').length > 0;
    return detected;
}"""

# ── GSAP interceptor — must be injected BEFORE page JS runs ───────────────
# Polls for async-loaded GSAP (ES module imports never set window.gsap)

GSAP_INTERCEPTOR = """() => {
    window.__taste_gsap_calls = [];
    window.__taste_gsap_timelines = [];
    window.__taste_gsap_intercepted = false;

    const install = () => {
        if (window.gsap && !window.__taste_gsap_intercepted) {
            window.__taste_gsap_intercepted = true;

            // Intercept gsap.to / gsap.from / gsap.fromTo
            ['to', 'from', 'fromTo', 'set'].forEach(method => {
                const orig = gsap[method].bind(gsap);
                gsap[method] = function(...args) {
                    window.__taste_gsap_calls.push({ method, args: JSON.stringify(args).slice(0, 500) });
                    return orig(...args);
                };
            });

            // Intercept gsap.timeline()
            const origTimeline = gsap.timeline.bind(gsap);
            gsap.timeline = function(config) {
                const tl = origTimeline(config);
                window.__taste_gsap_timelines.push({ config: JSON.stringify(config) });
                return tl;
            };
        }
    };

    // Install immediately (catches synchronous GSAP)
    install();

    // Poll for async-loaded GSAP (checks every 100ms for 20 seconds)
    const interval = setInterval(install, 100);
    setTimeout(() => clearInterval(interval), 20000);
}"""

# ── Virtual Scroll Telemetry ───────────────────────────────────────────────

VIRTUAL_SCROLL_OBSERVER = """() => {
    window.__taste_virtual_scroll = [];
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.attributeName === 'style') {
                const transform = mutation.target.style.transform;
                if (transform && (transform.includes('translate3d') || transform.includes('translateY') || transform.includes('translate(') || transform.includes('matrix'))) {
                    // Only log 1 in every 15 mutations to avoid massive arrays on 60fps scroll
                    if (Math.random() < 0.06) {
                        window.__taste_virtual_scroll.push({
                            type: "virtual_scroll_tick",
                            target: mutation.target.tagName,
                            className: mutation.target.className,
                            transform: transform
                        });
                    }
                }
            }
        });
    });
    // Start observer immediately on body
    if (document.body) {
        observer.observe(document.body, { attributes: true, subtree: true, attributeFilter: ['style'] });
    }
}"""

# ── CSS animation extractor ────────────────────────────────────────────────

CSS_ANIMATION_EXTRACTOR = """() => {
    const results = { keyframes: [], transitions: [], animations: [] };
    try {
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    if (rule.type === CSSRule.KEYFRAMES_RULE) {
                        results.keyframes.push(rule.cssText.slice(0, 300));
                    } else if (rule.style) {
                        if (rule.style.animation) {
                            results.animations.push({
                                selector: rule.selectorText,
                                animation: rule.style.animation
                            });
                        }
                        if (rule.style.transition) {
                            results.transitions.push({
                                selector: rule.selectorText,
                                transition: rule.style.transition
                            });
                        }
                    }
                }
            } catch(e) { /* Cross-origin sheet, skip */ }
        }
    } catch(e) {}
    return results;
}"""

# ── Scroll velocity profiler ───────────────────────────────────────────────

SCROLL_PROFILER = """() => {
    // Detect scroll-driven animation triggers by checking 
    // how many elements have transforms/opacity changes at scroll points
    const elements = document.querySelectorAll('[data-scroll], [data-aos], .aos-animate, [data-scroll-section]');
    return {
        scroll_driven_count: elements.length,
        data_aos: document.querySelectorAll('[data-aos]').length,
        scroll_magic: typeof ScrollMagic !== 'undefined',
        locomotive: !!document.querySelector('[data-scroll-container]'),
    };
}"""

# ── DOM structural & typography extractor ─────────────────────────────────

COMPUTED_STYLE_EXTRACTOR = """() => {
    const tags = {
        canvas: document.querySelectorAll('canvas').length,
        svg: document.querySelectorAll('svg').length,
        img: document.querySelectorAll('img').length,
        video: document.querySelectorAll('video').length,
        total_nodes: document.querySelectorAll('*').length
    };

    const elements = Array.from(document.querySelectorAll("h1, h2, h3, p, button, section, header, footer, nav"));
    const styles = [];
    for (const el of elements) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        
        styles.push({
            tag: el.tagName,
            fontSize: style.fontSize,
            fontWeight: style.fontWeight,
            letterSpacing: style.letterSpacing,
            lineHeight: style.lineHeight,
            color: style.color,
            backdropFilter: style.backdropFilter,
            transform: style.transform,
            zIndex: style.zIndex,
            bbox: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.width),
                h: Math.round(rect.height)
            }
        });
    }
    
    return {
        tags: tags,
        computed_styles: styles
    };
}"""


def scrape_site(url: str, site_id: str) -> dict:
    """
    Capture: screenshots, motion code, metadata.
    No video recording — 2 screenshots are sufficient for the taste model.
    Returns a summary dict. Raises on total failure.
    """
    site_dir = DATA_DIR / site_id
    site_dir.mkdir(parents=True, exist_ok=True)

    result = {"id": site_id, "url": url, "status": "failed"}

    has_media = (site_dir / "screenshot_hero.png").exists() and (site_dir / "screenshot_full.png").exists()

    context_options = {
        "viewport": VIEWPORT,
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        ),
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**context_options)
        page = context.new_page()

        try:
            # ── Inject GSAP interceptor before navigation ──────────────────
            page.add_init_script(GSAP_INTERCEPTOR)

            console.print(f"[cyan]→ Loading[/cyan] {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=90000)

            # Start Virtual Scroll Observer
            page.evaluate(VIRTUAL_SCROLL_OBSERVER)

            # Wait for fonts + heavy assets
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass  # timeout is fine — page is loaded enough

            time.sleep(3)  # Let entrance animations complete

            # ── WebGL / Audio Interaction Trigger ──────────────────────────
            # Many WebGL sites require a user click *anywhere* to start the experience
            try:
                page.mouse.click(VIEWPORT["width"] // 2, VIEWPORT["height"] // 2)
                time.sleep(1.5)
            except Exception:
                pass

            # ── Step 1: Dismiss cookie banners & modals ────────────────────
            dismissed = _dismiss_overlays(page)
            if dismissed:
                console.print(f"[dim]  ↳ Dismissed {dismissed} overlay(s)[/dim]")
                time.sleep(1)  # Let layout reflow after dismissal

            # ── Step 2: Hero screenshot (clean, no overlays) ───────────────
            # CRITICAL: Scroll to absolute top before capturing — scroll-restoration
            # on page load can offset the hero on scroll-hijacked sites.
            if not has_media:
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(0.5)
                page.screenshot(
                    path=str(site_dir / "screenshot_hero.png"),
                    clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": VIEWPORT["height"]},
                )

            # ── Step 3: Pre-scroll pass (triggers lazy loading) ───────────
            # Scroll through the whole page quickly to trigger lazy-loaded
            # images/sections, then scroll back to top for clean screenshots
            # Use robust height measurement — scroll libraries often return 0
            # for document.body.scrollHeight, so we check multiple sources.
            page_height = page.evaluate("""() => {
                return Math.max(
                    document.body.scrollHeight,
                    document.body.offsetHeight,
                    document.documentElement.clientHeight,
                    document.documentElement.scrollHeight,
                    document.documentElement.offsetHeight
                );
            }""")
            _lazy_load_pass(page, page_height)

            # Scroll back to top
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1.5)  # Let elements settle back

            # Re-dismiss any overlays that appeared during scroll
            _dismiss_overlays(page)
            time.sleep(0.5)

            # ── Step 4: Hover over nav links (triggers hover states) ───────
            nav_links = page.query_selector_all("nav a, header a, [role='navigation'] a")
            for link in nav_links[:5]:
                try:
                    link.hover(timeout=1000)
                    time.sleep(0.3)
                except Exception:
                    pass

            # Scroll back to top for full-page screenshot
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            # ── Step 5: Full page screenshot ───────────────────────────────
            # Always re-capture full page — scroll library neutralization
            # may work differently each time, and we need a correct capture.
            # Use stitched capture for scroll-hijacked sites (most reliable).
            # Falls back to full_page=True, then to hero screenshot.
            try:
                stitched_height = _capture_full_page_stitched(page, site_dir)
            except Exception as e:
                console.print(f"  [dim]  ↳ Stitched capture failed: {e}[/dim]")
                stitched_height = None

            if not stitched_height:
                try:
                    # Fallback: full_page=True for non-scroll-hijacked sites
                    _neutralize_scroll_libraries(page)
                    page.screenshot(
                        path=str(site_dir / "screenshot_full.png"),
                        full_page=True,
                    )
                except Exception as e:
                    # Last resort: copy hero screenshot as full page
                    console.print(f"  [dim]  ↳ Full page failed, using hero: {e}[/dim]")
                    import shutil
                    shutil.copy(site_dir / "screenshot_hero.png", site_dir / "screenshot_full.png")

            # ── Extract metadata ───────────────────────────────────────────
            title = page.title()
            description = page.evaluate("""() => {
                const m = document.querySelector('meta[name="description"], meta[property="og:description"]');
                return m ? m.content : '';
            }""")
            tech_stack = page.evaluate("""() => ({
                react:  typeof React !== 'undefined',
                next:   !!document.querySelector('#__NEXT_DATA__'),
                nuxt:   !!document.querySelector('#__nuxt'),
                webgl:  !!document.querySelector('canvas'),
                svelte: !!document.querySelector('[class^="svelte-"]'),
            })""")

            # ── Extract motion fingerprint ─────────────────────────────────
            motion_libs = page.evaluate(MOTION_FINGERPRINTS)
            css_motion  = page.evaluate(CSS_ANIMATION_EXTRACTOR)
            scroll_data = page.evaluate(SCROLL_PROFILER)
            dom_structure = page.evaluate(COMPUTED_STYLE_EXTRACTOR)

            # ── Collect intercepted GSAP calls & Virtual Scroll ─────────────
            gsap_calls     = page.evaluate("() => window.__taste_gsap_calls || []")
            gsap_timelines = page.evaluate("() => window.__taste_gsap_timelines || []")
            virtual_scroll = page.evaluate("() => window.__taste_virtual_scroll || []")

            # ── Bundle motion data ─────────────────────────────────────────
            motion_code = {
                "libraries_detected": motion_libs,
                "scroll_patterns":    scroll_data,
                "virtual_scroll":     virtual_scroll[:30], # cap to avoid huge files
                "gsap_calls":         gsap_calls[:30],   # cap at 30
                "gsap_timelines":     gsap_timelines[:10],
                "css_keyframes":      css_motion["keyframes"][:15],
                "css_animations":     css_motion["animations"][:20],
                "css_transitions":    css_motion["transitions"][:20],
            }

            # ── Save all data ──────────────────────────────────────────────
            metadata = {
                "id":          site_id,
                "url":         url,
                "title":       title,
                "description": description,
                "tech_stack":  tech_stack,
                "page_height": page_height,
                "dom_structure": dom_structure,
                "scraped_at":  time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

            (site_dir / METADATA_FILE).write_text(json.dumps(metadata, indent=2))
            (site_dir / MOTION_CODE_FILE).write_text(json.dumps(motion_code, indent=2))

            result.update({"status": "ok", "title": title, "motion_libs": motion_libs})
            console.print(f"[green]✓ Scraped[/green] {site_id} — {title}")

        except Exception as e:
            console.print(f"[red]✗ Failed[/red] {site_id}: {e}")
            result["error"] = str(e)
        finally:
            context.close()
            browser.close()

    return result


def _dismiss_overlays(page) -> int:
    """
    Auto-dismiss cookie banners, GDPR modals, newsletter popups.
    Tries multiple strategies. Returns number of elements dismissed.
    Supports: English, Italian, French, Spanish, German consent text.
    """
    def _try_native_click(el, p):
        try:
            # Same-frame measure + click — bounding box can shift between
            # measurement and click due to parallax on scroll-hijacked sites.
            box = el.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                p.mouse.move(x, y)
                p.mouse.click(x, y)
                return True
            else:
                el.click(timeout=1000)
                return True
        except Exception:
            # Fallback: CDP dispatch for stubborn gates that don't respond
            # to Playwright clicks (pointer-events:none overlays, canvas
            # event listeners that stopPropagation, etc.)
            try:
                box = el.bounding_box()
                if box:
                    x = box["x"] + box["width"] / 2
                    y = box["y"] + box["height"] / 2
                    cdp = p.context.new_cdp_session(p)
                    cdp.send("Input.dispatchMouseEvent", {
                        "type": "mousePressed", "x": x, "y": y,
                        "button": "left", "clickCount": 1
                    })
                    cdp.send("Input.dispatchMouseEvent", {
                        "type": "mouseReleased", "x": x, "y": y,
                        "button": "left", "clickCount": 1
                    })
                    return True
            except Exception:
                pass
            return False

    dismissed = 0

    # ── Strategy 1: Click accept/close buttons by text ────────────────────
    accept_texts = [
        # English
        "Accept all", "Accept All", "Accept cookies", "Accept Cookies",
        "I accept", "I agree", "Agree", "Got it", "OK", "Allow all",
        "Allow cookies", "Continue", "Close", "Dismiss",
        # Italian
        "Accetta", "Accetta tutti", "Accetta tutto", "Acconsento",
        "Chiudi", "Continua",
        # French
        "Accepter", "Tout accepter", "J'accepte", "Fermer",
        # Spanish
        "Aceptar", "Aceptar todo", "Cerrar",
        # German
        "Akzeptieren", "Alle akzeptieren", "Schließen",
    ]

    for text in accept_texts:
        try:
            btn = page.get_by_role("button", name=text, exact=False).first
            if btn.is_visible(timeout=500):
                if _try_native_click(btn, page):
                    dismissed += 1
                    time.sleep(0.4)
                    break
        except Exception:
            pass

    # ── Strategy 1.5: Awwwards "Enter Experience" / Intro Gates ─────────────
    enter_texts = [
        # English
        "Enter", "Enter site", "Enter experience", "Start", "Start experience",
        "Launch", "Play", "Discover", "Explore", "View site", "Click to enter",
        "Tap to enter", "Enter the site", "Enter in silence",
        # French (since site-059 is French)
        "Entrer", "Découvrir", "Explorer", "Commencer"
    ]

    # WebGL loaders often take 5-10 seconds to hit 100% and reveal the Start button.
    # We will poll for up to 10 seconds for these specific gates.
    for _ in range(10):
        for text in enter_texts:
            try:
                # We want exact=False to match "Enter the Experience" from "Enter"
                btn = page.get_by_role("button", name=text, exact=False).first
                if btn.is_visible(timeout=500):
                    if _try_native_click(btn, page):
                        dismissed += 1
                        time.sleep(2.0) # These often trigger big WebGL transitions, wait a bit
                        return dismissed
            except Exception:
                pass
            
            # Sometimes these aren't `<button>` tags, they are just `<a>` or `<div>`
            try:
                # case insensitive exact=False
                link = page.get_by_text(text, exact=False).first
                if link.is_visible(timeout=500):
                    if _try_native_click(link, page):
                        dismissed += 1
                        time.sleep(2.0)
                        return dismissed
            except Exception:
                pass
        
        time.sleep(1.0) # wait 1s before polling again for the loader to finish

    # ── Strategy 2: Common cookie banner CSS selectors ─────────────────────
    if dismissed == 0:
        cookie_selectors = [
            "[id*='cookie'] button",
            "[class*='cookie'] button",
            "[id*='consent'] button",
            "[class*='consent'] button",
            "[id*='gdpr'] button",
            "[class*='gdpr'] button",
            "[class*='banner'] button",
            "[class*='notice'] button[class*='accept']",
            "[data-testid*='cookie'] button",
            # Specific common CMPs
            "#onetrust-accept-btn-handler",
            ".cc-accept",
            ".cc-btn.cc-allow",
            "[aria-label*='cookie' i] button",
        ]
        for sel in cookie_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    if _try_native_click(el, page):
                        dismissed += 1
                        time.sleep(0.4)
                        break
            except Exception:
                pass

    # ── Strategy 3: Dismiss modal dialogs (non-cookie) ────────────────────
    modal_close_selectors = [
        "[role='dialog'] button[aria-label*='close' i]",
        "[role='dialog'] button[aria-label*='dismiss' i]",
        "[role='dialog'] [class*='close']",
        "[class*='modal'] [class*='close']",
        "[class*='popup'] [class*='close']",
        "[class*='overlay'] [class*='close']",
        "button[aria-label='Close']",
        "button[aria-label='close']",
        ".modal-close",
        ".popup-close",
    ]
    for sel in modal_close_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                if _try_native_click(el, page):
                    dismissed += 1
                    time.sleep(0.4)
                    break
        except Exception:
            pass

    # ── Strategy 4: Press Escape (catches many modals) ────────────────────
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        pass

    return dismissed


def _neutralize_scroll_libraries(page) -> int | None:
    """
    Neutralize Locomotive/Lenis before full-page screenshot.
    full_page=True produces broken stitches on scroll-hijacked sites
    because the library transforms the body and constrains height.

    Strategy: destroy the library, inject CSS to force body expansion,
    then measure and set explicit height.

    Returns the measured content height, or None if neutralization failed.
    """
    try:
        # Step 1: Destroy scroll libraries and inject CSS to force expansion
        page.evaluate("""
            () => {
                // Destroy Locomotive Scroll
                if (window.locomotive) {
                    try { window.locomotive.destroy(); } catch(e) {}
                }
                // Destroy Lenis
                if (window.lenis) {
                    try { window.lenis.destroy(); } catch(e) {}
                }

                // Inject CSS to force body expansion
                const style = document.createElement('style');
                style.id = 'taste-force-expand';
                style.textContent = `
                    html, body {
                        height: auto !important;
                        max-height: none !important;
                        overflow: visible !important;
                        transform: none !important;
                    }
                    [data-scroll-container], [data-scroll-section] {
                        height: auto !important;
                        max-height: none !important;
                        overflow: visible !important;
                        transform: none !important;
                    }
                    * {
                        transform: none !important;
                    }
                `;
                document.head.appendChild(style);

                // Scroll to absolute top
                window.scrollTo(0, 0);
            }
        """)
        time.sleep(1)

        # Step 2: Scroll to bottom to trigger lazy loading
        page.evaluate("""
            () => {
                window.scrollTo(0, document.body.scrollHeight);
            }
        """)
        time.sleep(1.5)

        # Step 3: Measure actual content height and set body height explicitly
        actual_height = page.evaluate("""
            () => {
                // Measure the actual content height by checking all elements
                let maxBottom = 0;
                const elements = document.querySelectorAll('body *');
                for (let i = 0; i < elements.length; i++) {
                    const rect = elements[i].getBoundingClientRect();
                    if (rect.bottom > maxBottom) {
                        maxBottom = rect.bottom;
                    }
                }
                // Also check documentElement
                const docHeight = document.documentElement.scrollHeight;
                const height = Math.max(maxBottom, docHeight, window.scrollY + window.innerHeight);

                // Set body height explicitly
                document.body.style.height = height + 'px';
                document.documentElement.style.height = height + 'px';

                // Scroll back to top
                window.scrollTo(0, 0);

                return Math.round(height);
            }
        """)
        time.sleep(0.5)

        if actual_height and actual_height > 900:
            console.print(f"  [dim]  ↳ Full page height: {actual_height}px (viewport was 900px)[/dim]")
            return actual_height

    except Exception as e:
        console.print(f"  [dim]  ↳ Scroll neutralization error: {e}[/dim]")

    return None


def _capture_full_page_stitched(page, site_dir: Path) -> int | None:
    """
    Capture full-page screenshot by stitching viewport screenshots.
    This is the most reliable approach for scroll-hijacked sites (Locomotive/Lenis)
    where full_page=True and clip don't work.

    Returns the total page height, or None if capture failed.
    """
    try:
        # Step 1: Neutralize scroll libraries and measure height
        actual_height = _neutralize_scroll_libraries(page)
        if not actual_height or actual_height <= 900:
            return None

        # Step 2: Capture viewport screenshots at different scroll positions
        viewport_h = 900
        screenshots = []
        scroll_y = 0

        while scroll_y < actual_height:
            page.evaluate(f"window.scrollTo(0, {scroll_y})")
            time.sleep(0.3)  # Let content settle

            screenshot_path = site_dir / f"_stitched_{scroll_y}.png"
            page.screenshot(path=str(screenshot_path))
            screenshots.append((scroll_y, screenshot_path))

            scroll_y += viewport_h

        # Step 3: Stitch screenshots together using PIL (memory-efficient)
        from PIL import Image

        # Create the stitched image
        stitched = Image.new('RGB', (1440, actual_height))

        for scroll_pos, path in screenshots:
            img = Image.open(path)
            try:
                # Calculate where this image should be placed
                if scroll_pos + viewport_h > actual_height:
                    # This is the last image — crop it to fit
                    remaining = actual_height - scroll_pos
                    if remaining > 0:
                        img = img.crop((0, 0, 1440, remaining))
                        stitched.paste(img, (0, scroll_pos))
                else:
                    stitched.paste(img, (0, scroll_pos))
            finally:
                img.close()  # Free memory immediately

        # Save the stitched image
        stitched.save(site_dir / "screenshot_full.png")
        stitched.close()

        # Clean up temporary screenshots
        for _, path in screenshots:
            try:
                path.unlink()
            except Exception:
                pass

        console.print(f"  [dim]  ↳ Stitched full page: {actual_height}px ({len(screenshots)} captures)[/dim]")
        return actual_height

    except Exception as e:
        console.print(f"  [dim]  ↳ Stitched capture error: {e}[/dim]")
        return None
    """
    Neutralize Locomotive/Lenis before full-page screenshot.
    full_page=True produces broken stitches on scroll-hijacked sites
    because the library transforms the body and constrains height.

    Strategy: destroy the library, inject CSS to force body expansion,
    then measure and set explicit height.

    Returns the measured content height, or None if neutralization failed.
    """
    try:
        # Step 1: Destroy scroll libraries and inject CSS to force expansion
        page.evaluate("""
            () => {
                // Destroy Locomotive Scroll
                if (window.locomotive) {
                    try { window.locomotive.destroy(); } catch(e) {}
                }
                // Destroy Lenis
                if (window.lenis) {
                    try { window.lenis.destroy(); } catch(e) {}
                }

                // Inject CSS to force body expansion
                const style = document.createElement('style');
                style.id = 'taste-force-expand';
                style.textContent = `
                    html, body {
                        height: auto !important;
                        max-height: none !important;
                        overflow: visible !important;
                        transform: none !important;
                    }
                    [data-scroll-container], [data-scroll-section] {
                        height: auto !important;
                        max-height: none !important;
                        overflow: visible !important;
                        transform: none !important;
                    }
                    * {
                        transform: none !important;
                    }
                `;
                document.head.appendChild(style);

                // Scroll to absolute top
                window.scrollTo(0, 0);
            }
        """)
        time.sleep(1)

        # Step 2: Scroll to bottom to trigger lazy loading
        page.evaluate("""
            () => {
                window.scrollTo(0, document.body.scrollHeight);
            }
        """)
        time.sleep(1.5)

        # Step 3: Measure actual content height and set body height explicitly
        actual_height = page.evaluate("""
            () => {
                // Measure the actual content height by checking all elements
                let maxBottom = 0;
                const elements = document.querySelectorAll('body *');
                for (let i = 0; i < elements.length; i++) {
                    const rect = elements[i].getBoundingClientRect();
                    if (rect.bottom > maxBottom) {
                        maxBottom = rect.bottom;
                    }
                }
                // Also check documentElement
                const docHeight = document.documentElement.scrollHeight;
                const height = Math.max(maxBottom, docHeight, window.scrollY + window.innerHeight);

                // Set body height explicitly
                document.body.style.height = height + 'px';
                document.documentElement.style.height = height + 'px';

                // Scroll back to top
                window.scrollTo(0, 0);

                return Math.round(height);
            }
        """)
        time.sleep(0.5)

        if actual_height and actual_height > 900:
            console.print(f"  [dim]  ↳ Full page height: {actual_height}px (viewport was 900px)[/dim]")
            return actual_height

    except Exception as e:
        console.print(f"  [dim]  ↳ Scroll neutralization error: {e}[/dim]")

    return None


def _lazy_load_pass(page, page_height: int) -> None:
    """
    Fast scroll pass to trigger lazy-loaded images and components.
    Uses instant scrolling so it doesn't pollute the video recording —
    only the subsequent paced scroll is recorded.
    """
    step = 400  # large steps = fast pass
    for y in range(0, min(page_height, 12000), step):
        page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'instant'}})")
        time.sleep(0.02)

    # Wait for lazy-triggered network requests to settle
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    time.sleep(0.5)


# ── Site list — ADD YOUR AWWWARDS URLs HERE ────────────────────────────────

SITES = [
    {"url": "https://example.invalid/", "id": "site-001"},
    {"url": "https://example.invalid/", "id": "site-002"},
    {"url": "https://example.invalid/", "id": "site-003"},
    {"url": "https://example.invalid/", "id": "site-004"},
    {"url": "https://example.invalid/", "id": "site-005"},
    {"url": "https://example.invalid/", "id": "site-006"},
    {"url": "https://example.invalid/", "id": "site-007"},
    {"url": "https://example.invalid/", "id": "site-008"},
    {"url": "https://example.invalid/", "id": "site-009"},
    {"url": "https://example.invalid/", "id": "site-010"},
    {"url": "https://example.invalid/", "id": "site-011"},
    {"url": "https://example.invalid/", "id": "site-012"},
    {"url": "https://example.invalid/", "id": "site-013"},
    {"url": "https://example.invalid/", "id": "site-014"},
    {"url": "https://example.invalid/", "id": "site-015"},
    {"url": "https://example.invalid/", "id": "site-016"},
    {"url": "https://example.invalid/", "id": "site-017"},
    {"url": "https://example.invalid/", "id": "site-018"},
    {"url": "https://example.invalid/", "id": "site-019"},
    {"url": "https://example.invalid/", "id": "site-020"},
    {"url": "https://example.invalid/", "id": "site-021"},
    {"url": "https://example.invalid/", "id": "site-022"},
    {"url": "https://example.invalid/", "id": "site-023"},
    {"url": "https://example.invalid/", "id": "site-024"},
    {"url": "https://example.invalid/", "id": "site-025"},
    {"url": "https://example.invalid/", "id": "site-026"},
    {"url": "https://example.invalid/", "id": "site-027"},
    {"url": "https://example.invalid/", "id": "site-028"},
    {"url": "https://example.invalid/", "id": "site-029"},
    {"url": "https://example.invalid/", "id": "site-030"},
    {"url": "https://example.invalid/", "id": "site-031"},
    {"url": "https://example.invalid/", "id": "site-032"},
    {"url": "https://example.invalid/", "id": "site-033"},
    {"url": "https://example.invalid/", "id": "site-034"},
    {"url": "https://example.invalid/", "id": "site-035"},
    {"url": "https://example.invalid/", "id": "site-036"},
    {"url": "https://example.invalid/", "id": "site-037"},
    {"url": "https://example.invalid/", "id": "site-038"},
    {"url": "https://example.invalid/", "id": "site-039"},
    {"url": "https://example.invalid/", "id": "site-040"},
    {"url": "https://example.invalid/", "id": "site-041"},
    {"url": "https://example.invalid/", "id": "site-042"},
    {"url": "https://example.invalid/", "id": "site-043"},
    {"url": "https://example.invalid/", "id": "site-044"},
    {"url": "https://example.invalid/", "id": "site-045"},
    {"url": "https://example.invalid/", "id": "site-046"},
    {"url": "https://example.invalid/", "id": "site-047"},
    {"url": "https://example.invalid/", "id": "site-048"},
    {"url": "https://example.invalid/", "id": "site-049"},
    {"url": "https://example.invalid/", "id": "site-050"},
    {"url": "https://example.invalid/", "id": "site-051"},
    {"url": "https://example.invalid/", "id": "site-052"},
    {"url": "https://example.invalid/", "id": "site-053"},
    {"url": "https://example.invalid/", "id": "site-054"},
    {"url": "https://example.invalid/", "id": "site-055"},
    {"url": "https://example.invalid/", "id": "site-056"},
    {"url": "https://example.invalid/", "id": "site-057"},
    {"url": "https://example.invalid/", "id": "site-058"},
    {"url": "https://example.invalid/", "id": "site-059"},
    {"url": "https://example.invalid/", "id": "site-060"},
    {"url": "https://example.invalid/", "id": "site-061"},
    {"url": "https://example.invalid/", "id": "site-062"},
    {"url": "https://example.invalid/", "id": "site-063"},
    {"url": "https://example.invalid/", "id": "site-064"},
    {"url": "https://example.invalid/", "id": "site-065"},
    {"url": "https://example.invalid/", "id": "site-066"},
    {"url": "https://example.invalid/", "id": "site-067"},
    {"url": "https://example.invalid/", "id": "site-068"},
    {"url": "https://example.invalid/", "id": "site-069"},
    {"url": "https://example.invalid/", "id": "site-070"},
    {"url": "https://example.invalid/", "id": "site-071"},
    {"url": "https://example.invalid/", "id": "site-072"},
    {"url": "https://example.invalid/", "id": "site-073"},
    {"url": "https://example.invalid/", "id": "site-074"},
    {"url": "https://example.invalid/", "id": "site-075"},
    {"url": "https://example.invalid/", "id": "site-076"},
    {"url": "https://example.invalid/", "id": "site-077"},
    {"url": "https://example.invalid/", "id": "site-078"},
    {"url": "https://example.invalid/", "id": "site-079"},
    {"url": "https://example.invalid/", "id": "site-080"},
    {"url": "https://example.invalid/", "id": "site-081"},
    {"url": "https://example.invalid/", "id": "site-082"},
    {"url": "https://example.invalid/", "id": "site-083"},
    {"url": "https://example.invalid/", "id": "site-084"},
    {"url": "https://example.invalid/", "id": "site-085"},
    {"url": "https://example.invalid/", "id": "site-086"},
    {"url": "https://example.invalid/", "id": "site-087"},
    {"url": "https://example.invalid/", "id": "site-088"},
    {"url": "https://example.invalid/", "id": "site-089"},
    {"url": "https://example.invalid/", "id": "site-090"},
    {"url": "https://example.invalid/", "id": "site-091"},
    {"url": "https://example.invalid/", "id": "site-092"},
    {"url": "https://example.invalid/", "id": "site-093"},
    {"url": "https://example.invalid/", "id": "site-094"},
    {"url": "https://example.invalid/", "id": "site-095"},
    {"url": "https://example.invalid/", "id": "site-096"},
    {"url": "https://example.invalid/", "id": "site-097"},
    {"url": "https://example.invalid/", "id": "site-098"},
    {"url": "https://example.invalid/", "id": "site-099"},
    {"url": "https://example.invalid/", "id": "site-100"},
]



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TASTE Scraper")
    parser.add_argument("--site", help="Scrape a single URL (e.g. --site https://example.invalid/ --id site-099)")
    parser.add_argument("--id", help="Site ID for --site flag")
    args = parser.parse_args()

    if args.site and args.id:
        scrape_site(args.site, args.id)
    else:
        for site in SITES:
            # We re-run scrape_site for all sites to inject the DOM extractor.
            # has_media check inside scrape_site will ensure we don't redownload massive images.
            scrape_site(site["url"], site["id"])
            time.sleep(1)  # be polite to servers
