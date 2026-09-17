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
DATA_DIR = Path("data")
LIST_MD = Path("../list.md")
VISION_MODEL = "ollama/minicpm-v" # or whatever the config says

VLM_PROMPT = """You are a mathematical aesthetic evaluator.
Analyze this web design screenshot and output EXACTLY a valid JSON object with 3 normalized scalar floats (0.0 to 1.0).
Do NOT write any markdown. Do NOT write any explanations.

{
  "intentionality_score": 0.0, // (0.0 = broken amateur CSS, 1.0 = highly deliberate, structural execution)
  "palette_cohesion": 0.0, // (0.0 = clashing/uncomplimentary, 1.0 = unified branding)
  "typographic_hierarchy": 0.0 // (0.0 = flat/undifferentiated, 1.0 = distinct visual scale and pacing)
}"""

def _dismiss_overlays(page) -> int:
    """Auto-dismiss cookie banners, GDPR modals, newsletter popups."""
    def _try_native_click(el, p):
        try:
            box = el.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                p.mouse.click(x, y)
                return True
            else:
                el.click(timeout=1000)
                return True
        except:
            return False

    dismissed = 0
    # Strategy 1: Buttons by text
    button_texts = [
        "Accept all", "Accept All", "Accept cookies", "Accept Cookies",
        "Allow cookies", "Continue", "Close", "Dismiss",
        "Launch", "Play", "Discover", "Explore", "View site", "Click to enter",
        "Enter", "Start"
    ]
    for text in button_texts:
        try:
            btn = page.get_by_role("button", name=re.compile(f"^{text}$", re.IGNORECASE)).first
            if btn.is_visible(timeout=500):
                if _try_native_click(btn, page):
                    dismissed += 1
        except: pass

    # Strategy 2: Common CSS selectors
    if dismissed == 0:
        cookie_selectors = [
            "[id*='cookie'] button", "[class*='cookie'] button",
            "[data-testid*='cookie'] button", "[aria-label*='cookie' i] button"
        ]
        for sel in cookie_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=500):
                    if _try_native_click(el, page):
                        dismissed += 1
            except: pass

    # Strategy 3: Modal dialogs
    modal_selectors = [
        "[role='dialog'] button[aria-label*='close' i]",
        "[role='dialog'] button[aria-label*='dismiss' i]",
        "[class*='modal'] [class*='close']",
        "[class*='popup'] [class*='close']",
        "[class*='overlay'] [class*='close']",
        "button[aria-label='Close']", "button[aria-label='close']"
    ]
    for sel in modal_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=500):
                if _try_native_click(el, page):
                    dismissed += 1
        except: pass

    return dismissed

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

def process_site(context, url, site_id):
    site_dir = DATA_DIR / site_id
    site_dir.mkdir(parents=True, exist_ok=True)
    hero_path = site_dir / "screenshot_hero.png"
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
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(2) # Stabilize

        # WebGL Bypass
        page.mouse.click(960, 540)
        page.keyboard.press("Escape")
        time.sleep(1)

        # Dismiss Modals
        dismissed = _dismiss_overlays(page)
        if dismissed:
            console.print(f"  [dim]↳ Dismissed {dismissed} overlays[/dim]")
            time.sleep(1)
        
        # Save Screenshot
        page.screenshot(path=str(hero_path))
        
        # Extract DOM Depth
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
        meta = {"url": url, "Total DOM depth": dom_depth}
        meta_path.write_text(json.dumps(meta, indent=2))
        
    except Exception as e:
        console.print(f"[red]✗ Playwright failed for {site_id}: {e}[/red]")
        return # Skip to next URL on hard failure
    finally:
        page.close() # CRITICAL: Free memory for the next URL

    # 2. OPENCV TELEMETRY
    try:
        metrics = analyzer.analyze_image(str(hero_path))
        vis_path.write_text(json.dumps(metrics, indent=2))
        console.print(f"  [green]↳ OpenCV metrics calculated[/green]")
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
            i_score = float(re.search(r'"intentionality_score"\s*:\s*([\d\.]+)', raw).group(1))
            c_score = float(re.search(r'"palette_cohesion"\s*:\s*([\d\.]+)', raw).group(1))
            t_score = float(re.search(r'"typographic_hierarchy"\s*:\s*([\d\.]+)', raw).group(1))
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
        browser = p.chromium.launch(headless=True)
        # Reusing the context prevents cookie/cache build-up while keeping the engine hot
        context = browser.new_context(viewport={"width": 1920, "height": 1080}) 
        
        for i, url in enumerate(urls, 1):
            site_id = f"site-{i:03d}"
            process_site(context, url, site_id)
            
        browser.close()

if __name__ == "__main__":
    main()
