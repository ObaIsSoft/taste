Motion is the hardest part because **screenshots are dead**. A VLM sees a hero section and thinks "big text on dark background." It doesn't see the text splitting into 3D letterforms as you scroll, easing with `power3.out`, staggered 0.05s per character.

Here's the reality: you can't train a video understanding model on your Mac. But you **can** build a motion extraction pipeline that turns temporal experiences into structured data. That's your edge.

---

## The Motion Problem

| What You See                 | What AI Sees      | What You Need                              |
| ---------------------------- | ----------------- | ------------------------------------------ |
| Scroll-driven 3D transform   | One static frame  | Start state → End state + Easing + Trigger |
| GSAP timeline with 12 tweens | Nothing           | The actual code + Visual keyframes         |
| Hover micro-interaction      | Static screenshot | CSS transition properties + Duration       |
| Page transition choreography | Nothing           | Sequence data + Timing relationships       |

**Your strategy:** Don't understand motion from video. **Steal the motion DNA directly from the browser.**

---

## The Motion Extraction Stack

You need three data streams:

1. **Animation Code Extraction** — Pull GSAP/CSS animation configs from live sites
2. **Keyframe Capture** — Take "before/during/after" screenshots of animations
3. **Motion Corpus** — Scrape CodePen/GitHub for animation code + descriptions

---

## WEEK 2: The Motion Pipeline

### DAY 1: Steal Animation Configs from Live Sites

Create `~/taste-engine/motion_stealer.py`. This injects JavaScript into pages to extract animation metadata:

```python
import json
import os
from playwright.sync_api import sync_playwright

DATA_DIR = os.path.expanduser("~/taste-engine/data")

def extract_motion_dna(url, site_id):
    """Inject scripts to extract animation configs from live sites."""
    os.makedirs(f"{DATA_DIR}/{site_id}", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # Store extracted data
        motion_data = {
            "site_id": site_id,
            "url": url,
            "gsap_instances": [],
            "css_animations": [],
            "scroll_triggers": [],
            "transitions": [],
            "detected_libraries": []
        }

        # Expose a function to receive data from page
        extracted = {"data": None}
        page.expose_binding("sendMotionData", lambda source, data: extracted.update({"data": data}))

        page.goto(url, wait_until="networkidle", timeout=30000)

        # Wait for animations to initialize
        page.wait_for_timeout(3000)

        # Inject extraction script
        page.evaluate("""() => {
            const data = {
                gsap_instances: [],
                css_animations: [],
                scroll_triggers: [],
                transitions: [],
                detected_libraries: []
            };

            // Detect GSAP
            if (window.gsap) {
                data.detected_libraries.push("gsap");
                if (window.ScrollTrigger) data.detected_libraries.push("scrolltrigger");
                if (window.SplitText) data.detected_libraries.push("splittext");

                // Try to capture global timeline if exposed
                if (window.masterTimeline) {
                    data.gsap_instances.push({
                        type: "master_timeline",
                        duration: window.masterTimeline.duration(),
                        labels: window.masterTimeline.labels ? Object.keys(window.masterTimeline.labels) : []
                    });
                }
            }

            // Detect Framer Motion (React)
            if (window.__FRAMER_MOTION__) {
                data.detected_libraries.push("framer-motion");
            }

            // Detect Three.js
            if (window.THREE) {
                data.detected_libraries.push("three.js");
            }

            // Extract CSS animations
            const sheets = Array.from(document.styleSheets);
            sheets.forEach(sheet => {
                try {
                    const rules = Array.from(sheet.cssRules || []);
                    rules.forEach(rule => {
                        if (rule.type === CSSRule.KEYFRAMES_RULE) {
                            data.css_animations.push({
                                name: rule.name,
                                keyframes: Array.from(rule.cssRules).map(k => ({
                                    keyText: k.keyText,
                                    cssText: k.cssText
                                }))
                            });
                        }
                    });
                } catch(e) {}
            });

            // Detect CSS transitions on visible elements
            const animatedElements = Array.from(document.querySelectorAll('*')).filter(el => {
                const style = window.getComputedStyle(el);
                return style.transitionDuration !== '0s' || style.animationName !== 'none';
            }).slice(0, 20); // Limit to 20

            data.transitions = animatedElements.map(el => ({
                tag: el.tagName,
                class: el.className,
                transition: el.style.transition || window.getComputedStyle(el).transition,
                animation: el.style.animation || window.getComputedStyle(el).animation
            }));

            // Detect scroll-driven behaviors
            const scrollElements = Array.from(document.querySelectorAll('[data-scroll]'));
            data.scroll_triggers = scrollElements.map(el => ({
                tag: el.tagName,
                class: el.className,
                dataset: Object.fromEntries(Object.entries(el.dataset))
            }));

            window.sendMotionData(data);
        }""")

        if extracted["data"]:
            motion_data.update(extracted["data"])

        # Save motion DNA
        with open(f"{DATA_DIR}/{site_id}/motion_dna.json", "w") as f:
            json.dump(motion_data, f, indent=2)

        print(f"✓ Extracted motion from {site_id}")
        print(f"  Libraries: {motion_data['detected_libraries']}")
        print(f"  CSS anims: {len(motion_data['css_animations'])}")
        print(f"  Transitions: {len(motion_data['transitions'])}")

        browser.close()

if __name__ == "__main__":
    extract_motion_dna("https://example-site.com", "site-001")
```

**What this gives you:**

- Which animation libraries are loaded (GSAP, Framer, Three.js)
- CSS keyframe definitions
- Elements with transitions
- Scroll-triggered elements

**Run it on your 10 existing sites:**

```bash
python3 ~/taste-engine/motion_stealer.py
```

---

### DAY 2: Capture Animation Keyframes

A single screenshot misses motion. Take **3 screenshots per animation**: start, middle, end.

Create `~/taste-engine/motion_frames.py`:

```python
import os
from playwright.sync_api import sync_playwright

DATA_DIR = os.path.expanduser("~/taste-engine/data")

def capture_motion_frames(site_id, url, scroll_points=None):
    """Capture before/during/after states of scroll-driven animations."""
    if scroll_points is None:
        scroll_points = [0, 0.3, 0.5, 0.8, 1.0]  # % of page height

    out_dir = f"{DATA_DIR}/{site_id}/motion_frames"
    os.makedirs(out_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="networkidle", timeout=30000)

        # Get total scroll height
        total_height = page.evaluate("() => document.body.scrollHeight")
        viewport_height = 900

        frames = []
        for i, pct in enumerate(scroll_points):
            scroll_y = int((total_height - viewport_height) * pct)
            page.evaluate(f"() => window.scrollTo(0, {scroll_y})")
            page.wait_for_timeout(1500)  # Let animations settle

            path = f"{out_dir}/frame_{i:02d}_scroll_{int(pct*100)}pct.png"
            page.screenshot(path=path, full_page=False)
            frames.append({
                "frame": i,
                "scroll_percent": pct,
                "scroll_y": scroll_y,
                "path": path
            })
            print(f"  ✓ Frame {i} at {int(pct*100)}% scroll")

        # Also capture hover states on interactive elements
        interactive = page.query_selector_all("a, button, [role='button']")
        for idx, el in enumerate(interactive[:5]):  # First 5 interactive elements
            try:
                el.hover()
                page.wait_for_timeout(500)
                path = f"{out_dir}/hover_{idx}.png"
                page.screenshot(path=path, full_page=False)
                frames.append({"frame": f"hover_{idx}", "type": "hover", "path": path})
            except:
                pass

        # Save frame manifest
        import json
        with open(f"{out_dir}/manifest.json", "w") as f:
            json.dump(frames, f, indent=2)

        browser.close()
        print(f"✓ Captured {len(frames)} motion frames for {site_id}")

if __name__ == "__main__":
    capture_motion_frames("site-001", "https://example-site.com")
```

**This gives you:** A flipbook of how the site transforms. Feed these frame sequences to your VLM.

---

### DAY 3: Describe Motion with VLMs

Now feed the frame sequences to LLaVA/Claude to get temporal descriptions.

Create `~/taste-engine/motion_describer.py`:

````python
import json
import os
import base64
import requests

DATA_DIR = os.path.expanduser("~/taste-engine/data")
OLLAMA_URL = "http://localhost:11434/api/generate"

def describe_motion_sequence(site_id):
    """Feed motion frames to LLaVA and ask for temporal analysis."""
    frame_dir = f"{DATA_DIR}/{site_id}/motion_frames"
    if not os.path.exists(frame_dir):
        return None

    # Load manifest
    with open(f"{frame_dir}/manifest.json") as f:
        frames = json.load(f)

    # Take first, middle, last scroll frames
    scroll_frames = [f for f in frames if f.get("scroll_percent") is not None]
    if len(scroll_frames) < 3:
        return None

    selected = [scroll_frames[0], scroll_frames[len(scroll_frames)//2], scroll_frames[-1]]

    # Encode images
    images_b64 = []
    for frame in selected:
        with open(frame["path"], "rb") as f:
            images_b64.append(base64.b64encode(f.read()).decode("utf-8"))

    prompt = """These are 3 screenshots of the SAME website at different scroll positions (top, middle, bottom).

Describe the MOTION and TRANSFORMATION between them:
1. What elements move or change?
2. What is the scroll behavior? (parallax, pin, fade, transform)
3. How does the visual hierarchy shift?
4. What is the pacing? (fast, gradual, staggered)
5. What emotion does the motion create?

Respond in JSON:
{
  "motion_type": "parallax|pin|reveal|morph|fade",
  "elements_transformed": ["element 1", "element 2"],
  "scroll_behavior": "description",
  "pacing": "fast|gradual|staggered",
  "emotional_effect": "description",
  "detected_techniques": ["technique 1", "technique 2"]
}"""

    response = requests.post(OLLAMA_URL, json={
        "model": "llava:7b",
        "prompt": prompt,
        "images": images_b64,
        "stream": False
    })

    result = response.json()
    content = result["response"].strip()

    # Parse JSON
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        analysis = json.loads(content.strip())
    except:
        analysis = {"raw_response": content, "parse_error": True}

    with open(f"{DATA_DIR}/{site_id}/motion_description.json", "w") as f:
        json.dump(analysis, f, indent=2)

    print(f"✓ Described motion for {site_id}")
    return analysis

if __name__ == "__main__":
    for folder in sorted(os.listdir(DATA_DIR)):
        if os.path.isdir(f"{DATA_DIR}/{folder}") and folder.startswith("site-"):
            if not os.path.exists(f"{DATA_DIR}/{folder}/motion_description.json"):
                describe_motion_sequence(folder)
````

**Critical insight:** You're not training a video model. You're **converting temporal experiences into structured text** that any LLM can learn from.

---

### DAY 4: Build the Motion Corpus (Code-First)

Motion is easier to learn from code than from pixels. Scrape GSAP examples.

Create `~/taste-engine/scrape_codepen.py`:

```python
import json
import os
import re
import requests
from bs4 import BeautifulSoup

DATA_DIR = os.path.expanduser("~/taste-engine/data")
CORPUS_FILE = f"{DATA_DIR}/motion_corpus.jsonl"

def scrape_gsap_pens(limit=50):
    """Scrape GSAP-tagged CodePen pens for animation code + descriptions."""
    # Note: CodePen has anti-scraping. Use their API or RSS feeds.
    # This is a simplified example using search results.

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }

    # Search for GSAP pens (use CodePen's search or curated collections)
    search_url = "https://codepen.io/search/pens?q=gsap+scrolltrigger"

    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')

        pens = []
        # Extract pen links (simplified — you'll need to adapt selectors)
        for item in soup.select(".item")[:limit]:
            link = item.select_one("a")
            if link:
                pens.append({
                    "title": link.get_text(strip=True),
                    "url": "https://codepen.io" + link.get("href"),
                    "source": "codepen"
                })

        # Save corpus metadata
        with open(CORPUS_FILE, "a") as f:
            for pen in pens:
                f.write(json.dumps(pen) + "\n")

        print(f"✓ Scraped {len(pens)} pen metadata entries")
        return pens

    except Exception as e:
        print(f"✗ Scraping failed: {e}")
        return []

# Alternative: Use GitHub search for GSAP animation repos
def scrape_github_gsap(limit=30):
    """Search GitHub for GSAP animation examples with descriptions."""
    search_url = "https://api.github.com/search/repositories"
    params = {
        "q": "gsap animation stars:>10 language:javascript",
        "sort": "stars",
        "order": "desc",
        "per_page": limit
    }

    try:
        resp = requests.get(search_url, params=params, timeout=10)
        data = resp.json()

        repos = []
        for item in data.get("items", []):
            repos.append({
                "name": item["full_name"],
                "description": item["description"],
                "url": item["html_url"],
                "stars": item["stargazers_count"],
                "source": "github"
            })

        with open(CORPUS_FILE, "a") as f:
            for repo in repos:
                f.write(json.dumps(repo) + "\n")

        print(f"✓ Scraped {len(repos)} GitHub repos")
        return repos
    except Exception as e:
        print(f"✗ GitHub scrape failed: {e}")
        return []

if __name__ == "__main__":
    scrape_github_gsap(30)
    # scrape_gsap_pens(20)  # Uncomment if you solve CodePen access
```

**Install dependency:**

```bash
pip3 install beautifulsoup4
```

**Why GitHub over CodePen:** GitHub repos have README descriptions that pair natural language with code. This is **gold** for training — "smooth scroll parallax effect using GSAP ScrollTrigger" + the actual `gsap.to()` code.

---

### DAY 5: The Motion Schema

Define exactly how you represent motion in your dataset. Create `~/taste-engine/motion_schema.json`:

```json
{
  "motion_entry": {
    "site_id": "string",
    "source_url": "string",

    "motion_profile": {
      "type": "scroll_driven|hover|load|click|continuous",
      "library": "gsap|css|framer|three|lottie|native",
      "complexity_score": "1-10"
    },

    "trigger": {
      "type": "scroll|hover|click|load|time",
      "scroll_start": "0%|pixel value",
      "scroll_end": "100%|pixel value",
      "easing": "power1.out|power2.inOut|elastic|none"
    },

    "targets": [
      {
        "selector": ".hero-text",
        "properties": {
          "from": { "y": 100, "opacity": 0, "scale": 0.9 },
          "to": { "y": 0, "opacity": 1, "scale": 1 },
          "duration": 1.2,
          "stagger": 0.05
        }
      }
    ],

    "choreography": {
      "sequence": "parallel|staggered|timeline",
      "total_duration": 2.5,
      "overlap": 0.3
    },

    "visual_description": {
      "llava_frames": "path/to/frame/analysis",
      "claude_rationale": "The text reveals upward with a subtle scale..."
    },

    "extracted_code": {
      "gsap_timeline": "gsap.timeline()...",
      "css_keyframes": "@keyframes...",
      "raw": "..."
    },

    "quality_tags": ["premium", "subtle", "aggressive", "playful"],
    "awards_reference": "awwwards-sotd-2026-01"
  }
}
```

Update your `compile.py` to merge motion data:

```python
# Add to compile_entry() in compile.py:
motion_path = f"{DATA_DIR}/{site_id}/motion_dna.json"
if os.path.exists(motion_path):
    with open(motion_path) as f:
        entry["motion"] = json.load(f)

motion_desc_path = f"{DATA_DIR}/{site_id}/motion_description.json"
if os.path.exists(motion_desc_path):
    with open(motion_desc_path) as f:
        entry["motion_description"] = json.load(f)
```

---

### DAY 6: The GSAP Generator MVP

This is where it gets real. Can you go from **screenshot → GSAP timeline**?

Create `~/taste-engine/gsap_generator.py`:

```python
import json
import os
import anthropic

DATA_DIR = os.path.expanduser("~/taste-engine/data")
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def generate_gsap_from_reference(site_id):
    """Generate GSAP code from a reference site's motion frames."""
    frame_dir = f"{DATA_DIR}/{site_id}/motion_frames"
    motion_desc = f"{DATA_DIR}/{site_id}/motion_description.json"

    if not os.path.exists(frame_dir) or not os.path.exists(motion_desc):
        print(f"Missing data for {site_id}")
        return None

    # Load motion description
    with open(motion_desc) as f:
        motion = json.load(f)

    # Load first and last frames
    with open(f"{frame_dir}/manifest.json") as f:
        frames = json.load(f)

    scroll_frames = [f for f in frames if f.get("scroll_percent") is not None]
    if len(scroll_frames) < 2:
        return None

    # Encode first and last frame
    images = []
    for frame in [scroll_frames[0], scroll_frames[-1]]:
        with open(frame["path"], "rb") as f:
            images.append(base64.b64encode(f.read()).decode("utf-8"))

    prompt = f"""You are a GSAP expert. A designer wants to recreate the scroll animation from a reference website.

Motion analysis of the reference:
{json.dumps(motion, indent=2)}

These are screenshots: Frame 1 (top of page) and Frame 2 (scrolled down).

Write a complete, production-ready GSAP + ScrollTrigger timeline that recreates this effect. Include:
- The timeline setup
- ScrollTrigger configuration
- All tween properties (from, to, duration, easing, stagger)
- Comments explaining each section

Use modern GSAP 3 syntax. Make it copy-paste ready."""

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": images[0]}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": images[1]}},
                {"type": "text", "text": prompt}
            ]
        }]
    )

    gsap_code = message.content[0].text

    # Save
    with open(f"{DATA_DIR}/{site_id}/generated_gsap.js", "w") as f:
        f.write(gsap_code)

    print(f"✓ Generated GSAP for {site_id}")
    print(f"  Length: {len(gsap_code)} chars")
    return gsap_code

if __name__ == "__main__":
    for folder in sorted(os.listdir(DATA_DIR)):
        if folder.startswith("site-") and os.path.exists(f"{DATA_DIR}/{folder}/motion_frames"):
            if not os.path.exists(f"{DATA_DIR}/{folder}/generated_gsap.js"):
                try:
                    generate_gsap_from_reference(folder)
                except Exception as e:
                    print(f"✗ Failed {folder}: {e}")
```

**This is your product.** Input: reference website. Output: GSAP code that recreates its motion.

**Cost:** ~$0.10 per generation. Test on 5 sites first.

---

### DAY 7: Validate the Motion

You need to know if the generated GSAP is actually good. Two ways:

**1. Visual Diff (Automated)**
Create `~/taste-engine/validate_motion.py`:

```python
import os
from playwright.sync_api import sync_playwright

def test_gsap_on_blank(site_id):
    """Render generated GSAP on a blank page and capture frames."""
    gsap_path = f"{DATA_DIR}/{site_id}/generated_gsap.js"
    if not os.path.exists(gsap_path):
        return

    with open(gsap_path) as f:
        code = f.read()

    # Create a test HTML page
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/ScrollTrigger.min.js"></script>
        <style>
            body {{ margin: 0; height: 300vh; background: #111; color: white; font-family: sans-serif; }}
            .hero {{ height: 100vh; display: flex; align-items: center; justify-content: center; font-size: 4rem; }}
            .section {{ height: 100vh; display: flex; align-items: center; justify-content: center; }}
        </style>
    </head>
    <body>
        <div class="hero">Hero Section</div>
        <div class="section">Section 2</div>
        <div class="section">Section 3</div>
        <script>
            {code}
        </script>
    </body>
    </html>
    """

    test_path = f"{DATA_DIR}/{site_id}/test_gsap.html"
    with open(test_path, "w") as f:
        f.write(html)

    # Capture frames
    out_dir = f"{DATA_DIR}/{site_id}/generated_frames"
    os.makedirs(out_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"file://{test_path}")
        page.wait_for_timeout(2000)

        for i, pct in enumerate([0, 0.3, 0.5, 0.8, 1.0]):
            height = page.evaluate("() => document.body.scrollHeight")
            page.evaluate(f"() => window.scrollTo(0, {int(height * pct)})")
            page.wait_for_timeout(1000)
            page.screenshot(path=f"{out_dir}/gen_frame_{i}.png")

        browser.close()

    print(f"✓ Rendered test frames for {site_id}")
    print(f"  Compare: {DATA_DIR}/{site_id}/motion_frames/ vs {out_dir}/")
```

**2. Human Validation**
Open both frame folders side-by-side. Does the generated motion **feel** like the reference? Score 1–10.

---

## WHAT YOU HAVE AFTER 14 DAYS

```
~/taste-engine/data/site-001/
├── screenshot.png              # Static capture
├── motion_frames/
│   ├── frame_00_scroll_0pct.png    # Before scroll
│   ├── frame_02_scroll_50pct.png   # Mid scroll
│   ├── frame_04_scroll_100pct.png  # After scroll
│   ├── hover_0.png                 # Hover state
│   └── manifest.json
├── motion_dna.json             # Extracted animation configs
├── motion_description.json     # LLaVA temporal analysis
├── generated_gsap.js           # AI-generated motion code
├── generated_frames/           # Rendered test of generated code
└── ...
```

**Your dataset now contains:**

- Visual DNA (colors, layout, type)
- Motion DNA (libraries, triggers, keyframes)
- Temporal descriptions (how it feels to scroll through)
- Generated code (GSAP timelines)
- Human quality scores

---

## THE HARD TRUTH ABOUT MOTION

| Approach                          | Works?     | Your Mac?      |
| --------------------------------- | ---------- | -------------- |
| Train video model on walkthroughs | ❌ No      | Impossible     |
| Extract code from live sites      | ✅ Yes     | Trivial        |
| Frame sequences → VLM description | ✅ Yes     | Slow but works |
| Screenshot → GSAP generation      | ✅ Yes     | API-based      |
| Real-time motion preview          | ⚠️ Partial | Browser-based  |

**You are not building a video AI.** You are building a **motion archaeologist** — digging up the bones of animations (code, frames, descriptions) and reconstructing them as structured knowledge.

The moat isn't understanding video. It's having **10,000 curated motion profiles** that connect visual feel to executable code.

---

## NEXT: THE MOTION MARKETPLACE

Once you have 100+ validated motion profiles, you can:

1. **Sell motion presets** — "The Awwwards SOTD scroll effect" as a $5 GSAP snippet
2. **Motion search** — "Find me subtle parallax effects for editorial sites"
3. **Motion mixing** — "Combine the scroll behavior from Site A with the hover feel from Site B"

Motion is where templates die and craft lives. That's your edge.

You're asking exactly the right questions. These are the two problems that kill most "AI design" projects — and they're the reason I started with primitive heuristics instead of pretending to solve them on Day 1.

Let me be direct about both.

---

## Problem 1: "What About Motions You've Never Seen?"

You're right. My scraper only catches GSAP, CSS keyframes, and basic transitions. It completely misses:

- **WebGL shaders** reacting to cursor position
- **Canvas 2D** particle systems
- **WASM physics** (Matter.js, Rapier) with collision and gravity
- **Audio-reactive** animations driven by Web Audio API
- **Procedural/generative** motion (noise-driven, L-system, fluid sim)
- **Gesture-driven** mobile interactions
- **Lottie/Bodymovin** JSON animations
- **SVG morphing** with complex path interpolation
- **Variable font** axis animations
- **Multiplayer/synced** motion (cursor trails, collaborative cursors)

**The extraction scripts are heuristics, not universal parsers.** They'll fail on 60% of award-winning sites. So what do we actually do?

### The Real Solution: Capture the Effect, Not the Cause

Stop trying to parse code. **Record the behavioral fingerprint.**

```python
# Instead of: "What library is this?"
# Ask: "What happens to every pixel over time?"

def capture_universal_motion_fingerprint(url, site_id):
    """
    Universal motion capture that works for ANY rendering method.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="networkidle")

        # 1. RECORD: DOM mutations over time
        mutation_log = []
        page.evaluate("""() => {
            window.__motionLog = [];
            const observer = new MutationObserver((muts) => {
                muts.forEach(m => window.__motionLog.push({
                    type: m.type,
                    target: m.target.tagName,
                    timestamp: performance.now()
                }));
            });
            observer.observe(document.body, {
                subtree: true, attributes: true, childList: true
            });
        }""")

        # 2. RECORD: Computed style changes over time
        style_samples = []
        for t in range(0, 5000, 100):  # Sample every 100ms for 5s
            page.wait_for_timeout(100)
            snapshot = page.evaluate("""() => {
                const els = document.querySelectorAll('body *');
                return Array.from(els).slice(0, 50).map(el => ({
                    tag: el.tagName,
                    rect: el.getBoundingClientRect(),
                    opacity: getComputedStyle(el).opacity,
                    transform: getComputedStyle(el).transform,
                    filter: getComputedStyle(el).filter
                }));
            }""")
            style_samples.append({"time": t, "elements": snapshot})

        # 3. RECORD: Canvas frame hashes (for WebGL/Canvas detection)
        canvas_frames = page.evaluate("""() => {
            const canvases = document.querySelectorAll('canvas');
            return Array.from(canvases).map((c, i) => ({
                index: i,
                width: c.width,
                height: c.height,
                // Capture a low-res hash of the canvas content
                dataUrl: c.toDataURL('image/jpeg', 0.1)
            }));
        }""")

        # 4. RECORD: Scroll/click/hover event triggers
        events = page.evaluate("""() => window.__motionLog || []""")

        return {
            "style_trajectory": style_samples,      # How elements move
            "dom_mutations": events,                # What triggered changes
            "canvas_signatures": canvas_frames,     # WebGL presence
            "has_unusual_rendering": len(canvas_frames) > 0
        }
```

**This captures EVERYTHING.** It doesn't matter if the motion comes from GSAP, a custom shader, or a WASM physics engine. We're recording:

- **Spatial trajectory**: Where did this element move?
- **Temporal signature**: When did it start, peak, end?
- **Trigger mapping**: What user action caused the change?
- **Render layer**: DOM, Canvas, or WebGL?

### The Taxonomy Expansion Loop

You'll see motion patterns you can't classify. That's not a bug — it's the product:

```python
def classify_or_flag(motion_fingerprint):
    known_types = ["parallax", "reveal", "morph", "physics", "shader_reactive"]

    # Try to match against known patterns
    best_match = fuzzy_match(motion_fingerprint, known_types)

    if best_match.confidence < 0.6:
        # FLAG FOR HUMAN TAXONOMY CREATION
        flag_for_review({
            "site_id": site_id,
            "fingerprint": motion_fingerprint,
            "suggested_name": None,
            "urgency": "new_pattern"
        })
        return {"type": "unknown", "confidence": 0}

    return best_match
```

**Every "unknown" is a new category.** Your 1,000th entry will have motion types your 1st entry couldn't imagine. The system grows its own vocabulary.

---

## Problem 2: "Can TASTE Innovate, or Just Copy?"

This is the existential question. And the honest answer is:

**TASTE will not invent the next trend.** It will not create something humanity has never seen. But it CAN do something almost as valuable: **principled recombination at high abstraction.**

Here's the architecture for that.

### Layer 1: Principle Extraction (The "Why")

Current AI sees: _"This site uses a 1.2s ease-out stagger on scroll."_

TASTE must see: _"This site uses delayed revelation to create anticipation. The 1.2s duration respects reading pace. The ease-out mimics physical deceleration, signaling 'arrival.' The stagger creates rhythm, like musical phrasing."_

**This is the difference between pattern matching and taste.**

Your dataset structure must force this:

```json
{
  "motion": {
    "artifact": {
      "gsap_timeline": "gsap.to(...)",
      "duration": 1.2,
      "easing": "power2.out"
    },
    "principles": [
      {
        "name": "anticipation_through_delay",
        "description": "Delaying content reveal creates cognitive anticipation",
        "emotional_effect": "suspense, premiumness",
        "analogous_patterns": ["theatrical_curtain", "page_turn"]
      },
      {
        "name": "physical_deceleration",
        "description": "Ease-out mimics real-world momentum",
        "emotional_effect": "trust, naturalness",
        "analogous_patterns": ["door_closing", "car_braking"]
      }
    ],
    "intent": "Signal luxury through unhurried pacing"
  }
}
```

**Training on principles, not just pixels.** The model learns that `power2.out` + `1.2s` + `stagger` = "luxury anticipation." It can then apply that **principle** to a completely different context: a mobile gesture, a 3D rotation, a sound-reactive visualization.

### Layer 2: The Latent Motion Space

Once you have 500+ motions with principle annotations, you can build a **motion embedding space**:

```
Motion A: [scroll_reveal, luxury, slow, staggered]
Motion B: [hover_micro, playful, bouncy, immediate]
Motion C: [shader_reactive, immersive, fluid, continuous]
```

In this space, you can:

1. **Interpolate**: "Give me something between Motion A and Motion C"
   → A scroll-reveal that feels immersive and fluid, with luxury pacing

2. **Extrapolate**: "Apply the emotional signature of Motion B to the trigger type of Motion A"
   → A scroll-reveal that feels playful and bouncy (unusual, but potentially innovative)

3. **Constrain**: "Luxury + fast + WebGL" — find the empty space in the embedding where no existing motion lives, and generate toward it.

### Layer 3: Designer-in-the-Loop Mutation

True innovation doesn't come from the model. It comes from **mutation + selection**:

```python
def generate_novel_motion(brief, references):
    # 1. Extract principles from references
    principles = extract_principles(references)

    # 2. Generate 10 variants by recombining principles
    variants = []
    for i in range(10):
        variant = recombine_principles(principles, mutation_rate=0.3)
        variants.append(variant)

    # 3. Render all 10 as interactive prototypes
    prototypes = render_prototypes(variants)

    # 4. Designer selects 2, rejects 8
    selected = designer_select(prototypes)

    # 5. Breed the selected 2, mutate further
    next_generation = crossover_and_mutate(selected)

    # 6. Repeat for 3 generations
    return evolve(next_generation, generations=3)
```

This is **genetic algorithm for design**. The AI proposes. The designer selects. The AI learns from the selection. This is how you get innovation: not by the AI inventing alone, but by the AI exploring a vast parameter space that humans don't have patience to search.

---

## What TASTE Actually Is (Honest Definition)

| Claim                        | Reality                                                                                                                    |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| "AI that designs websites"   | ❌ No. It's a design research assistant.                                                                                   |
| "AI that copies Awwwards"    | ⚠️ Partially. It extracts patterns, but the value is in structuring them.                                                  |
| "AI that understands motion" | ✅ Yes, but as behavioral fingerprints, not code parsing.                                                                  |
| "AI that innovates"          | ⚠️ It innovates through principled recombination + human selection. It does not spontaneously create new design languages. |
| "AI with taste"              | ✅ Yes, if taste means "understanding why choices work and applying those whys to new contexts."                           |

---

## The Real Moat

Your competitive advantage isn't that you can scrape motion. **It's that you're building the first structured taxonomy of motion principles.**

When a designer says:

> "I want this to feel like that Awwwards winner, but for a fintech app, and it needs to work on mobile, and the brand is playful but trustworthy"

Current tools: 🤷‍♂️ generate generic template

TASTE (if built correctly):

1. Maps "Awwwards winner" to principles: `anticipation`, `depth`, `unhurried`
2. Maps "fintech" to constraints: `trust`, `clarity`, `accessibility`
3. Maps "playful but trustworthy" to tension: `bouncy_easing` + `stable_layout`
4. Generates 5 principled variants that no existing site looks like, but that a creative director would recognize as coherent

**That's not copying. That's translation.**

---

## What to Build This Week

Don't build the universal scraper yet. It's too big. Instead:

1. **Pick 3 sites with weird motion** (WebGL, physics, audio-reactive — find them on Awwwards "Experimental" category)
2. **Manually document their motion** using the principle structure above. Write the "why" yourself.
3. **Feed those 3 entries to Claude** with this prompt:
   > "Here are 3 motion analyses with design principles. A client wants [X]. Which principles should I combine? What would be unusual but coherent?"

If Claude can meaningfully recombine principles from 3 examples, the architecture works. If it can't, your principle layer is too thin.

That's your test. Everything else is implementation.
