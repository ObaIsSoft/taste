It's been a month since the brief. You still have the same MacBook. Here's your **exact Day 1–7 playbook** — copy-pasteable, no theory, just movement.

---

## BEFORE YOU START

**Accept your constraints:**

- 16GB RAM = you curate data and run small models locally. You do NOT train.
- 512GB SSD = you can store ~15,000 screenshots + metadata comfortably.
- M1 Pro = great for local inference with Ollama, terrible for fine-tuning.

**Your only goal this week:** Get 50 curated Awwwards entries into a structured JSON database with AI-generated design rationale. That's it.

---

## DAY 0: Environment (30 minutes)

Open Terminal. Run these exactly:

```bash
# 1. Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install core tools
brew install python@3.11 git node ollama

# 3. Install Playwright for scraping
pip3 install playwright pillow requests colorthief
playwright install chromium

# 4. Install Ollama and pull a vision model
ollama pull llava:7b

# 5. Make a project folder
mkdir -p ~/taste-engine/data
cd ~/taste-engine
```

**Verify Ollama works:**

```bash
ollama run llava:7b "Describe this image" ~/taste-engine/data/test.jpg
```

(If you don't have a test image, skip — we'll generate one tomorrow.)

---

## DAY 1: Build the Scraper (2–3 hours)

Create `~/taste-engine/scraper.py`:

```python
import json
import os
import time
from playwright.sync_api import sync_playwright
from PIL import Image

DATA_DIR = os.path.expanduser("~/taste-engine/data")

def scrape_site(url, site_id):
    """Capture screenshot and basic metadata of a website."""
    os.makedirs(f"{DATA_DIR}/{site_id}", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(5)  # Let WebGL/animations settle

            # Full page screenshot
            page.screenshot(path=f"{DATA_DIR}/{site_id}/screenshot.png", full_page=True)

            # Get basic metadata
            title = page.title()
            description = page.evaluate("""() => {
                const meta = document.querySelector('meta[name="description"]');
                return meta ? meta.content : '';
            }""")

            metadata = {
                "id": site_id,
                "url": url,
                "title": title,
                "description": description,
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(f"{DATA_DIR}/{site_id}/metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            print(f"✓ Saved {site_id}")

        except Exception as e:
            print(f"✗ Failed {site_id}: {e}")
        finally:
            browser.close()

# Example usage — replace with real Awwwards URLs
if __name__ == "__main__":
    sites = [
        {"url": "https://example-awwwards-site.com", "id": "site-001"},
        {"url": "https://another-premium-site.com", "id": "site-002"},
    ]
    for site in sites:
        scrape_site(site["url"], site["id"])
        time.sleep(2)  # Be polite
```

**Your job today:**

1. Go to [awwwards.com/websites](https://www.awwwards.com/websites)
2. Pick 10 sites you think are beautiful
3. Add their URLs to the `sites` list in the script
4. Run: `python3 ~/taste-engine/scraper.py`
5. Verify you have 10 folders in `~/taste-engine/data/` each with `screenshot.png` and `metadata.json`

---

## DAY 2: Extract Visual DNA (2 hours)

Create `~/taste-engine/analyzer.py`:

```python
import json
import os
from PIL import Image
from colorthief import ColorThief

DATA_DIR = os.path.expanduser("~/taste-engine/data")

def analyze_image(site_id):
    """Extract basic visual properties from screenshot."""
    img_path = f"{DATA_DIR}/{site_id}/screenshot.png"
    if not os.path.exists(img_path):
        return None

    img = Image.open(img_path)
    width, height = img.size

    # Extract dominant colors
    color_thief = ColorThief(img_path)
    palette = color_thief.get_palette(color_count=5)

    analysis = {
        "dimensions": {"width": width, "height": height},
        "aspect_ratio": round(width / height, 2),
        "dominant_colors": [
            {"rgb": c, "hex": "#{:02x}{:02x}{:02x}".format(*c)}
            for c in palette
        ],
        "file_size_kb": round(os.path.getsize(img_path) / 1024, 2)
    }

    with open(f"{DATA_DIR}/{site_id}/visual_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)

    return analysis

if __name__ == "__main__":
    for folder in os.listdir(DATA_DIR):
        if os.path.isdir(f"{DATA_DIR}/{folder}"):
            result = analyze_image(folder)
            if result:
                print(f"✓ Analyzed {folder}")
```

**Run it:**

```bash
python3 ~/taste-engine/analyzer.py
```

**What you now have:** For each site, color palette + dimensions + file info.

---

## DAY 3: Local AI Vision (3–4 hours)

Create `~/taste-engine/vision_llm.py`:

````python
import json
import os
import base64
import requests

DATA_DIR = os.path.expanduser("~/taste-engine/data")
OLLAMA_URL = "http://localhost:11434/api/generate"

def analyze_with_llava(site_id):
    """Send screenshot to local LLaVA model for design analysis."""
    img_path = f"{DATA_DIR}/{site_id}/screenshot.png"

    # Read image as base64
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = """Analyze this website screenshot as a senior UI designer. Provide ONLY a JSON object with these keys:
- layout_type (e.g. "asymmetric grid", "centered hero", "split screen")
- typography_style (e.g. "editorial serif", "geometric sans", "brutalist monospace")
- color_mood (e.g. "dark luxury", "pastel playful", "high contrast corporate")
- motion_impression (e.g. "static", "subtle parallax", "heavy WebGL", "scroll-driven")
- aesthetic_category (e.g. "brutalist", "minimal", "editorial", "futuristic", "corporate")
- notable_elements (array of strings, e.g. ["oversized typography", "3D product render", "custom cursor"])

Respond with ONLY valid JSON. No markdown, no explanations."""

    response = requests.post(OLLAMA_URL, json={
        "model": "llava:7b",
        "prompt": prompt,
        "images": [img_b64],
        "stream": False
    })

    result = response.json()

    # Try to parse JSON from response
    try:
        content = result["response"].strip()
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        analysis = json.loads(content.strip())
    except:
        analysis = {"raw_response": result["response"], "parse_error": True}

    with open(f"{DATA_DIR}/{site_id}/llava_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)

    print(f"✓ LLaVA analyzed {site_id}")
    return analysis

if __name__ == "__main__":
    # Make sure Ollama is running: ollama serve
    for folder in sorted(os.listdir(DATA_DIR)):
        if os.path.isdir(f"{DATA_DIR}/{folder}"):
            if not os.path.exists(f"{DATA_DIR}/{folder}/llava_analysis.json"):
                analyze_with_llava(folder)
                time.sleep(1)
````

**Before running, start Ollama server in a new Terminal tab:**

```bash
ollama serve
```

**Then run:**

```bash
python3 ~/taste-engine/vision_llm.py
```

**Reality check:** LLaVA 7B will hallucinate. Some outputs will be garbage. That's fine. You're building the pipeline, not the final model. Fix the prompt over 2–3 iterations.

---

## DAY 4: Structured Master Database (2 hours)

Create `~/taste-engine/compile.py`:

```python
import json
import os

DATA_DIR = os.path.expanduser("~/taste-engine/data")
MASTER_FILE = f"{DATA_DIR}/master_dataset.jsonl"

def compile_entry(site_id):
    """Merge all data sources into one structured record."""
    entry = {"id": site_id}

    # Load metadata
    meta_path = f"{DATA_DIR}/{site_id}/metadata.json"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            entry["metadata"] = json.load(f)

    # Load visual analysis
    visual_path = f"{DATA_DIR}/{site_id}/visual_analysis.json"
    if os.path.exists(visual_path):
        with open(visual_path) as f:
            entry["visual"] = json.load(f)

    # Load LLaVA analysis
    llava_path = f"{DATA_DIR}/{site_id}/llava_analysis.json"
    if os.path.exists(llava_path):
        with open(llava_path) as f:
            entry["llava"] = json.load(f)

    # Placeholder for human/Claude enrichment
    entry["design_rationale"] = None
    entry["quality_score"] = None
    entry["tags"] = []

    return entry

if __name__ == "__main__":
    with open(MASTER_FILE, "w") as out:
        for folder in sorted(os.listdir(DATA_DIR)):
            if os.path.isdir(f"{DATA_DIR}/{folder}") and folder.startswith("site-"):
                entry = compile_entry(folder)
                out.write(json.dumps(entry) + "\n")
                print(f"✓ Compiled {folder}")

    print(f"\nMaster dataset saved to {MASTER_FILE}")
```

**Run it:**

```bash
python3 ~/taste-engine/compile.py
```

**Check your data:**

```bash
wc -l ~/taste-engine/data/master_dataset.jsonl
head -1 ~/taste-engine/data/master_dataset.jsonl | python3 -m json.tool
```

You should see a rich JSON object with metadata, visual DNA, and LLaVA's design reading.

---

## DAY 5: Add the Taste Layer (Claude API) (2–3 hours)

Sign up for [Anthropic Console](https://console.anthropic.com). Get $5 in free credits.

Create `~/taste-engine/enrich_claude.py`:

````python
import json
import os
import base64
import anthropic

DATA_DIR = os.path.expanduser("~/taste-engine/data")
MASTER_FILE = f"{DATA_DIR}/master_dataset.jsonl"
# Put your key here or use export ANTHROPIC_API_KEY=...
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def enrich_with_claude(site_id, entry):
    """Use Claude to write expert design rationale."""
    img_path = f"{DATA_DIR}/{site_id}/screenshot.png"

    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    # Build context from LLaVA
    llava_context = json.dumps(entry.get("llava", {}), indent=2)

    prompt = f"""You are a creative director at a top digital agency. A junior designer analyzed this award-winning website with an AI vision model. Here is the AI's analysis:

{llava_context}

Look at the screenshot and write a professional design rationale covering:
1. Why the layout works (grid logic, visual hierarchy, whitespace)
2. Why the typography choices support the brand
3. How color psychology is used
4. What motion/interaction approach is implied
5. What makes this feel "premium" vs. templated

Respond in JSON format:
{{
  "design_rationale": "2-3 paragraphs...",
  "key_patterns": ["pattern 1", "pattern 2"],
  "premium_signals": ["signal 1", "signal 2"],
  "suggested_tokens": {{
    "primary_color": "#...",
    "font_pairing": "Heading Font / Body Font",
    "spacing_base": "8px or 4px"
  }}
}}"""

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                {"type": "text", "text": prompt}
            ]
        }]
    )

    # Try to extract JSON
    content = message.content[0].text
    try:
        # Find JSON block
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        rationale = json.loads(content.strip())
    except:
        rationale = {"raw_response": content, "parse_error": True}

    return rationale

if __name__ == "__main__":
    # Read master file
    entries = []
    with open(MASTER_FILE) as f:
        for line in f:
            entries.append(json.loads(line))

    for entry in entries:
        sid = entry["id"]
        if entry.get("design_rationale") is not None:
            print(f"Skip {sid}")
            continue

        print(f"Enriching {sid}...")
        try:
            rationale = enrich_with_claude(sid, entry)
            entry["design_rationale"] = rationale
            entry["enriched_at"] = __import__('time').strftime("%Y-%m-%d %H:%M:%S")

            # Save back
            with open(f"{DATA_DIR}/{sid}/claude_rationale.json", "w") as f:
                json.dump(rationale, f, indent=2)
            print(f"✓ Enriched {sid}")
        except Exception as e:
            print(f"✗ Failed {sid}: {e}")

    # Rewrite master
    with open(MASTER_FILE, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    print("Done.")
````

**Install the Anthropic SDK:**

```bash
pip3 install anthropic
```

**Set your key:**

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

**Run:**

```bash
python3 ~/taste-engine/enrich_claude.py
```

**Cost:** ~$0.05 per site. 10 sites = $0.50.

---

## DAY 6: Human Validation (2 hours)

You are now the **taste filter**. Open each screenshot. Read the Claude rationale. Score it.

Create `~/taste-engine/validate.py`:

```python
import json
import os

DATA_DIR = os.path.expanduser("~/taste-engine/data")
MASTER_FILE = f"{DATA_DIR}/master_dataset.jsonl"

def validate_entry(site_id):
    """Interactive validation — you score the AI's analysis."""
    entry_path = f"{DATA_DIR}/{site_id}/claude_rationale.json"
    if not os.path.exists(entry_path):
        return None

    with open(entry_path) as f:
        rationale = json.load(f)

    print(f"\n{'='*50}")
    print(f"SITE: {site_id}")
    print(f"{'='*50}")
    print(json.dumps(rationale, indent=2)[:800] + "...")

    score = input("Quality score (1-10, or 's' to skip): ").strip()
    if score == 's':
        return None

    tags = input("Tags (comma separated, e.g. webgl,editorial,minimal): ").strip()

    return {
        "quality_score": int(score),
        "tags": [t.strip() for t in tags.split(",") if t.strip()]
    }

if __name__ == "__main__":
    # Read current master
    entries = {}
    with open(MASTER_FILE) as f:
        for line in f:
            e = json.loads(line)
            entries[e["id"]] = e

    for sid in sorted(entries.keys()):
        if entries[sid].get("quality_score"):
            continue
        result = validate_entry(sid)
        if result:
            entries[sid]["quality_score"] = result["quality_score"]
            entries[sid]["tags"] = result["tags"]

            # Save incremental
            with open(MASTER_FILE, "w") as f:
                for e in entries.values():
                    f.write(json.dumps(e) + "\n")
            print(f"✓ Saved {sid}")
```

**Run it:**

```bash
python3 ~/taste-engine/validate.py
```

**Your standard:**

- **8–10:** Keep. This analysis is genuinely useful.
- **5–7:** Keep but flag for prompt improvement.
- **1–4:** Delete or re-run with better prompt context.

---

## DAY 7: Review & Iterate (2 hours)

**Check your numbers:**

```bash
cd ~/taste-engine/data
echo "Total entries:"
wc -l master_dataset.jsonl

echo "Entries with quality scores:"
grep -c '"quality_score": [0-9]' master_dataset.jsonl

echo "Average score:"
python3 -c "
import json
scores = []
with open('master_dataset.jsonl') as f:
    for line in f:
        e = json.loads(line)
        if e.get('quality_score'):
            scores.append(e['quality_score'])
print(f'Average: {sum(scores)/len(scores):.1f}' if scores else 'No scores yet')
"
```

**If you have 10+ entries with scores ≥7:**

- You have a **seed dataset**.
- Next week: Scale to 50. Refine prompts based on what scored high.

**If most scores are <6:**

- Your LLaVA prompt is too vague. Make it more specific.
- Claude is getting bad context. Improve the prompt chaining.
- Your Awwwards picks might be too complex for 7B models. Start with simpler sites.

---

## WHAT YOU HAVE AFTER 7 DAYS

```
~/taste-engine/
├── data/
│   ├── site-001/
│   │   ├── screenshot.png
│   │   ├── metadata.json
│   │   ├── visual_analysis.json
│   │   ├── llava_analysis.json
│   │   └── claude_rationale.json
│   ├── site-002/
│   │   └── ...
│   └── master_dataset.jsonl   ← Your goldmine
├── scraper.py
├── analyzer.py
├── vision_llm.py
├── compile.py
├── enrich_claude.py
└── validate.py
```

**This is not a product. This is proof you can do it.** If you get to 50 curated entries with quality scores, you have something worth talking about. If you quit on Day 3, you saved yourself 6 months of delusion.

---

## NEXT WEEK (if you survive)

1. **Scale to 50 entries.** Use the same pipeline.
2. **Build a simple Figma plugin** that reads your `master_dataset.jsonl` and shows reference cards.
3. **Post your learnings** on X or Designer News. Tag it "Building an AI with taste."

The only wrong move is not starting. Your Mac is ready. The code is above. Go.
