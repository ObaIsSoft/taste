import os
import json
import time
import re
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from litellm import completion
from rich.console import Console

import analyzer # from analyzer.py

console = Console()
DATA_DIR = Path("../data")
LIST_MD = Path("../../list.md")
VISION_MODEL = "ollama/minicpm-v" # or whatever the config says

VLM_PROMPT = """You are a mathematical aesthetic evaluator.
Analyze this web design screenshot and output EXACTLY a valid JSON object with 3 normalized scalar floats (0.0 to 1.0).
Do NOT write any markdown. Do NOT write any explanations.

{
  "intentionality_score": 0.0, // (0.0 = broken amateur CSS, 1.0 = highly deliberate, structural execution)
  "palette_cohesion": 0.0, // (0.0 = clashing/uncomplimentary, 1.0 = unified branding)
  "typographic_hierarchy": 0.0 // (0.0 = flat/undifferentiated, 1.0 = distinct visual scale and pacing)
}"""

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

def _dismiss_overlays(page) -> int:
    """Auto-dismiss cookie banners, GDPR modals, newsletter popups, age gates."""
    def _try_native_click(el, p):
        try:
            box = el.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                p.mouse.move(x, y)
                p.mouse.click(x, y)
                return True
            else:
                el.click(timeout=1000)
                return True
        except:
            return False

    dismissed = 0
    # Strategy 1: Buttons by text (Multi-lingual + Age Gates)
    accept_texts = [
        # English
        "Accept all", "Accept All", "Accept cookies", "Accept Cookies",
        "I accept", "I agree", "Agree", "Got it", "OK", "Allow all",
        "Allow", "Accept", "Yes", "Save", "Back", "Save Preferences",
        "Allow cookies", "Continue", "Close", "Dismiss",
        # Italian
        "Accetta", "Accetta tutti", "Accetta tutto", "Acconsento",
        "Chiudi", "Continua", "Si", "Sì",
        # French
        "Accepter", "Tout accepter", "J'accepte", "Fermer", "Oui",
        # Spanish
        "Aceptar", "Aceptar todo", "Cerrar", "Sí",
        # German
        "Akzeptieren", "Alle akzeptieren", "Schließen", "Ja",
    ]
    for text in accept_texts:
        try:
            # Tolerate surrounding whitespace but require exact word match
            btn = page.get_by_role("button", name=re.compile(rf"^\s*{text}\s*$", re.IGNORECASE)).first
            if btn.is_visible(timeout=200):
                if _try_native_click(btn, page):
                    dismissed += 1
                    time.sleep(0.4)
                    break
        except: pass
        
        try:
            link = page.get_by_text(re.compile(rf"^\s*{text}\s*$", re.IGNORECASE)).first
            if link.is_visible(timeout=200):
                if _try_native_click(link, page):
                    dismissed += 1
                    time.sleep(0.4)
                    break
        except: pass

    # Strategy 1.5: Awwwards "Enter Experience" / Intro Gates
    enter_texts = [
        "Enter", "Enter site", "Enter experience", "Start", "Start experience",
        "Launch", "Play", "Discover", "Explore", "View site", "Click to enter",
        "Tap to enter", "Enter the site", "Enter in silence",
        "Entrer", "Découvrir", "Explorer", "Commencer"
    ]
    # Poll for up to 10 seconds for these specific gates
    for _ in range(10):
        for text in enter_texts:
            try:
                btn = page.get_by_role("button", name=text, exact=False).first
                if btn.is_visible(timeout=500):
                    if _try_native_click(btn, page):
                        dismissed += 1
                        time.sleep(2.0)
                        return dismissed
            except: pass
            
            try:
                link = page.get_by_text(text, exact=False).first
                if link.is_visible(timeout=500):
                    if _try_native_click(link, page):
                        dismissed += 1
                        time.sleep(2.0)
                        return dismissed
            except: pass
        time.sleep(1.0) # Wait 1s before polling again for loader to finish

    # Strategy 2: Common CSS selectors
    if dismissed == 0:
        cookie_selectors = [
            "[id*='cookie'] button", "[class*='cookie'] button",
            "[id*='consent'] button", "[class*='consent'] button",
            "[id*='gdpr'] button", "[class*='gdpr'] button",
            "[class*='banner'] button", "[class*='notice'] button[class*='accept']",
            "[data-testid*='cookie'] button",
            "#onetrust-accept-btn-handler", ".cc-accept", ".cc-btn.cc-allow",
            "[aria-label*='cookie' i] button"
        ]
        for sel in cookie_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=500):
                    if _try_native_click(el, page):
                        dismissed += 1
                        time.sleep(0.4)
                        break
            except: pass

    global_x_selectors = [
        "button[aria-label*='close' i]", "button[aria-label*='dismiss' i]", "button[aria-label*='back' i]",
        "[class*='close']", "[class*='dismiss']", "[class*='back-btn']", "[class*='back-button']",
        "[id*='close']", "svg[class*='close']", "svg[class*='cross']",
        "button:has(svg[class*='close'])", "a[class*='close']", "div[class*='close-btn']",
        "*:has-text('X')", "*:has-text('✕')", "*:has-text('✖')",
        "*:has-text('Close')", "*:has-text('CLOSE')", "*:has-text('CLOSE X')", "*:has-text('Back')"
    ]
    for sel in global_x_selectors:
        try:
            locs = page.locator(sel).all()
            for loc in locs:
                if loc.is_visible(timeout=200):
                    # For *:has-text, make sure we only click the specific innermost element, not the whole page
                    if loc.evaluate("el => el.children.length === 0 || el.tagName === 'BUTTON' || el.tagName === 'A'"):
                        if _try_native_click(loc, page):
                            dismissed += 1
                            time.sleep(0.3)
        except: pass

    # Strategy 4: Bruteforce text match on links and buttons
    if dismissed == 0:
        for text in accept_texts:
            try:
                # Use strict exact match for the catch-all to avoid catastrophic misclicks
                locs = page.locator(f"button:text-is('{text}'), a:text-is('{text}'), [role='button']:text-is('{text}')").all()
                for loc in locs:
                    if loc.is_visible(timeout=200):
                        if _try_native_click(loc, page):
                            dismissed += 1
            except: pass

    # Catch-all: Press Escape
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except: pass

    return dismissed

def _nuke_overlays(page) -> None:
    """Aggressive fallback: delete modals, cookie banners, and backdrops directly from the DOM."""
    try:
        page.evaluate("""
            () => {
                const elements = document.querySelectorAll('div, section, aside, dialog');
                for (let el of elements) {
                    if (el.tagName === 'BODY' || el.tagName === 'HTML' || el.tagName === 'HEADER' || el.tagName === 'NAV') continue;
                    
                    const style = window.getComputedStyle(el);
                    const zIndex = parseInt(style.zIndex);
                    const isFixed = style.position === 'fixed' || style.position === 'sticky' || style.position === 'absolute';
                    
                    // Identify if element explicitly screams "I am a modal"
                    const idClass = (el.id + ' ' + el.className).toLowerCase();
                    const isModalRelated = idClass.includes('cookie') || idClass.includes('consent') || 
                                           idClass.includes('modal') || idClass.includes('popup') || 
                                           idClass.includes('gdpr') || idClass.includes('banner');
                                           
                    // Nuke known modal wrappers
                    if (isModalRelated && isFixed) {
                        el.remove();
                        continue;
                    }
                    
                    // Nuke extraordinarily high z-index fixed elements that cover a huge area 
                    // (>40 is usually a popup/modal, lead gen card, not a hero background)
                    if (isFixed && !isNaN(zIndex) && zIndex > 40) {
                        const rect = el.getBoundingClientRect();
                        // If it takes up more than 20% of the screen but isn't a header (height < 150)
                        if (rect.width * rect.height > (window.innerWidth * window.innerHeight * 0.2) && rect.height > 150) {
                            el.remove();
                        }
                    }
                }
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            }
        """)
        time.sleep(0.5)
    except: pass

def _lazy_load_pass(page):
    """Scroll down and up using mouse wheel to trigger lazy-loaded images/animations safely without breaking WebGL canvases."""
    try:
        page.mouse.wheel(0, 1000)
        time.sleep(1.0)
        page.mouse.wheel(0, 1000)
        time.sleep(1.0)
        page.mouse.wheel(0, -2000)
        time.sleep(1.0)
    except: pass

def parse_urls():
    content = LIST_MD.read_text()
    urls = []
    seen = set()
    for line in content.splitlines():
        match = re.search(r'https?://[^\s]+', line.strip())
        if match:
            u = match.group(0)
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls

VIEWPORT = {"width": 1920, "height": 1080}

def process_site(context, url, site_id):
    site_dir = DATA_DIR / site_id
    # Skip if we already successfully captured this site
    has_screenshot = (site_dir / "screenshot_hero.png").exists() and (site_dir / "screenshot_full.png").exists()
    has_metadata = (site_dir / "metadata.json").exists()
    hero_path = site_dir / "screenshot_hero.png"
    full_path = site_dir / "screenshot_full.png"
    meta_path = site_dir / "metadata.json"
    vis_path = site_dir / "visual_analysis.json"
    vlm_path = site_dir / "structured_analysis.json"

    if vlm_path.exists():
        console.print(f"[dim]⏭ {site_id} already processed.[/dim]")
        return

    console.print(f"\n[bold cyan]Processing {site_id}: {url}[/bold cyan]")

    # 1. PLAYWRIGHT CAPTURE (Using injected context)
    page = context.new_page()
    try:
        # Load page and wait for heavy assets
        page.goto(url, wait_until="load", timeout=30000)
        time.sleep(25) # Stabilize much longer for heavy media/3D assets

        # WebGL / Audio Interaction Trigger
        try:
            # Click top-left corner instead of dead-center to avoid accidentally 
            # clicking a 'Preferences' or 'Cookie Policy' link on a centered banner!
            page.mouse.click(10, 10)
            time.sleep(1.5)
        except: pass

        # Dismiss Modals
        dismissed = _dismiss_overlays(page)
        if dismissed > 0:
            console.print(f"  [dim]↳ Dismissed {dismissed} overlays. Waiting for potential WebGL animations...[/dim]")
            time.sleep(10.0)
            
        # Nuke anything that survived (e.g. stubborn lead gen cards)
        _nuke_overlays(page)
        
        # --- CRITICAL: HERO SCREENSHOT BEFORE SCROLLING ---
        # Awwwards sites use Locomotive/Lenis custom scrolling. If we synthetically scroll down,
        # it permanently offsets the WebGL canvas on many sites (like Bellussi), resulting in a blank white screen.
        # We MUST capture the viewport right now while it is perfectly pristine.
        page.evaluate("window.scrollTo(0, 0)") # Ensure we are at the absolute top
        time.sleep(1.0)
        page.screenshot(
            path=str(hero_path),
            clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": VIEWPORT["height"]},
            animations="disabled"
        )
        
        # Lazy Load Pass
        _lazy_load_pass(page)

        # Full Page Screen Capture
        page.screenshot(
            path=str(full_path),
            full_page=True,
            animations="disabled"
        )
        
        # Extract DOM Depth & V1 Metadata
        dom_depth = page.evaluate("""
            () => {
                let maxDepth = 0;
                function traverse(node, depth) {
                    if (depth > maxDepth) maxDepth = depth;
                    for (let child of node.children) traverse(child, depth + 1);
                }
                traverse(document.body, 1);
                return maxDepth;
            }
        """)
        dom_structure = page.evaluate(COMPUTED_STYLE_EXTRACTOR)
        meta = {
            "url": url, 
            "Total DOM depth": dom_depth,
            "dom_structure": dom_structure,
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        meta_path.write_text(json.dumps(meta, indent=2))
        
    except Exception as e:
        console.print(f"[red]✗ Playwright failed for {site_id}: {e}[/red]")
        return # Skip to next URL on hard failure
    finally:
        page.close() # CRITICAL: Free memory for the next URL

    # 2. OPENCV TELEMETRY
    try:
        metrics = analyzer.analyze_image(site_id)
        if metrics:
            vis_path.write_text(json.dumps(metrics, indent=2))
            console.print(f"  [green]↳ OpenCV metrics calculated[/green]")
        else:
            console.print(f"  [yellow]⚠ OpenCV returned None for {site_id}[/yellow]")

    except Exception as e:
        console.print(f"[red]✗ OpenCV failed for {site_id}: {e}[/red]")
        return

    # 3. VLM STRUCTURED EXTRACTION
    try:
        with open(hero_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        response = completion(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": VLM_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]
            }],
            temperature=0.1
        )
        raw = response.choices[0].message.content.strip()
        
        # Try standard JSON parse
        try:
            if raw.startswith("```"):
                raw = raw.split("```")[1].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()
            raw = raw.strip().rstrip("```")
            vlm_data = json.loads(raw)
            
        except json.JSONDecodeError:
            # Robust Fallback: Regex extraction if VLM hallucinates formatting
            console.print("[yellow]⚠ JSON parse failed, utilizing regex extraction fallback...[/yellow]")
            def extract_float(pattern, text):
                m = re.search(pattern, text)
                return float(m.group(1)) if m else 0.5
                
            i_score = extract_float(r'"intentionality_score"\s*:\s*([\d\.]+)', raw)
            c_score = extract_float(r'"palette_cohesion"\s*:\s*([\d\.]+)', raw)
            t_score = extract_float(r'"typographic_hierarchy"\s*:\s*([\d\.]+)', raw)
            vlm_data = {
                "intentionality_score": i_score,
                "palette_cohesion": c_score,
                "typographic_hierarchy": t_score
            }

        vlm_path.write_text(json.dumps(vlm_data, indent=2))
        console.print(f"  [green]↳ VLM extracted: I:{vlm_data.get('intentionality_score')} C:{vlm_data.get('palette_cohesion')} H:{vlm_data.get('typographic_hierarchy')}[/green]")
        
    except Exception as e:
        console.print(f"[red]✗ VLM failed for {site_id}: {e}[/red]")
        vlm_path.write_text(json.dumps({"intentionality_score": 0.5, "palette_cohesion": 0.5, "typographic_hierarchy": 0.5}, indent=2))

def main():
    DATA_DIR.mkdir(exist_ok=True)
    urls = parse_urls()
    console.print(f"[bold green]Found {len(urls)} URLs in list.md[/bold green]")
    
    # HOISTED BROWSER INSTANTIATION
    with sync_playwright() as p:
        # Add GPU flags to ensure WebGL/Three.js heavy sites (like Bellussi) render correctly in headless mode
        # We use headless=False to allow actual GPU rendering of 3D WebGL scenes.
        browser = p.chromium.launch(
            headless=True,
            executable_path="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            args=[
                "--ignore-gpu-blocklist",
                "--use-gl=angle",
                "--use-angle=gl",
                "--enable-webgl",
                "--enable-gpu-rasterization"
            ]
        )
        
        # Spoof a real Mac Safari/Chrome user agent to bypass bot detection
        context = browser.new_context(
            viewport={"width": VIEWPORT["width"], "height": VIEWPORT["height"]},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        )
        
        # Stealth: Hide navigator.webdriver flag so Awwwards sites don't block the WebGL canvas
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})") 
        
        for i, url in enumerate(urls, 1):
            site_id = f"site-{i:03d}"
            process_site(context, url, site_id)
            
        browser.close()

if __name__ == "__main__":
    main()
