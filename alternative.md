The failure is not merely a script bug; it is an **architectural anti-pattern**.

You are asking a single 8-billion parameter model to act as a layout engine, a DOM parser, an OCR system, and a high-caliber Creative Director all in a single forward pass. Because an 8B model lacks the cross-attention capacity to correlate raw CSS code with 5 separate high-resolution visual token grids, it defaults to the lowest-energy basin in its pretraining weights: **design marketing platitudes** (_"clean, modern, strategic whitespace"_).

To build training-grade ground truth for a future foundation model, you must **decouple deterministic measurement from qualitative synthesis**.

---

### The 3 Structural Mistakes in the Current Approach

1. **The "Persona Trap" (Subjectivity vs. Measurement):**
   When you prompt an 8B model to _"Critique this like a world-class designer,"_ you activate the model's chat/roleplay weights rather than its visual grounding weights. The model generates tokens that _sound_ like a review, rather than verifying what is physically present on the canvas.
2. **Vision Token Flooding:**
   One 1080p hero image plus four scroll frames generates thousands of image patch tokens. When concatenated with hundreds of lines of raw CSS and JS, the vision-to-language projection layer loses needle-in-a-haystack resolution. Large visual landmarks (like a full-bleed face or an Awwwards badge) blur into the background noise of the attention matrix.
3. **Using an LLM for What an AST/Browser Already Knows:**
   Feeding raw CSS/JS into a vision model to understand styling is computationally wasteful. A headless browser already knows the exact computed styles, bounding boxes, DOM tree depth, and animation curves with 100% mathematical accuracy.

---

### The New Architecture: Decoupled Multi-Stage Extraction

Do not ask the LLM to inspect pixels for things the DOM can report, and do not ask the VLM to write qualitative essays.

```
┌────────────────────────────────────────────────────────┐
│ STAGE 1: Deterministic Engine (Headless Browser / AST) │
│ - Computed CSS: Typography scale, line-heights         │
│ - Color extraction (K-Means on canvas)                 │
│ - Motion telemetry (GSAP easing curves, durations)     │
└──────────────────────────┬─────────────────────────────┘
                           │ Outputs: Verified Fact Sheet
┌──────────────────────────▼─────────────────────────────┐
│ STAGE 2: Constrained VLM (MiniCPM-V / Qwen-VL)          │
│ - 1 Image at a time (Hero only, or Keyframe only)      │
│ - Zero subjective questions                            │
│ - Strictly extracts visual inventory & layout geometry  │
└──────────────────────────┬─────────────────────────────┘
                           │ Outputs: Structured Visual Schema
┌──────────────────────────▼─────────────────────────────┐
│ STAGE 3: Taste Synthesizer (Text-only Gemma / Qwen)    │
│ - Input: Structured Fact Sheet + Visual Schema         │
│ - Task: Contrast winners vs. losers using exact data   │
└────────────────────────────────────────────────────────┘

```

---

### 1. Stage 1: Offload Styling to Playwright (Deterministic Truth)

Stop asking the VLM if the site uses "glassmorphism" or what the typography is. Extract the computed style sheet programmatically via your scraper:

```javascript
// Run inside page.evaluate() during crawl
const getComputedDesignTokens = () => {
  const elements = Array.from(
    document.querySelectorAll("h1, h2, p, button, section"),
  );

  return elements.map((el) => {
    const style = window.getComputedStyle(el);
    return {
      tag: el.tagName,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      letterSpacing: style.letterSpacing,
      lineHeight: style.lineHeight,
      color: style.color,
      backdropFilter: style.backdropFilter, // Captures exact blur/glassmorphism
      transform: style.transform,
    };
  });
};
```

_Result:_ You now have ground-truth numbers (e.g., `backdropFilter: blur(24px)`, `letterSpacing: -0.04em`, `modular-scale: 1.333`) without a single hallucination.

---

### 2. Stage 2: Turn the VLM from an "Art Critic" into an "Evidence Inspector"

Feed the VLM **one frame at a time**. Strip all design philosophy from the system prompt. Treat the model like a forensic camera system that outputs strict JSON describing what physically exists.

**Bad Prompt (Causes Mode Collapse):**

> _"Act as an elite Creative Director. Critique the aesthetic quality, layout, typography, and visual hierarchy of this website hero section."_

**Engineered Prompt (Forces Visual Grounding):**

```markdown
Analyze the image. Output a valid JSON object strictly matching this schema:
{
"focal_subject": {
"type": "human_face | 3d_render | product_mockup | pure_typography | abstract_graphic",
"description": "Short factual description of the main focal element",
"bounding_box_normalized": [ymin, xmin, ymax, xmax]
},
"background_style": {
"type": "flat_color | gradient | textured | video_still | photographic",
"dominant_hue": "hex or descriptive name",
"has_grain_or_noise": boolean
},
"badges_and_overlays": [
"List any award ribbons, floating badges, floating tags, or sticky navbars visible"
],
"whitespace_distribution": "dense | balanced | extreme_empty_space"
}

Do not use words like 'clean', 'modern', or 'polished'. State only observable visual facts.
```

By constraining the model to concrete object categorization and bounding boxes, MiniCPM-V cannot evade the task with generic adjectives. If there is a massive cinematic face, it is forced to populate the `"focal_subject"` field.

---

### 3. Stage 3: The Synthesizer Prompt (Gemma / Qwen)

Once you have the programmatic DOM metrics and the factual VLM visual tags, compile them into a unified **Design Specification Sheet** (~400 tokens) and feed it to your text model to extract the "Taste Tokens":

```markdown
You are analyzing verified structural data from a top-tier Awwwards website.

METRIC SHEET:

- Dominant Background: Photographic (Cinematic human face at [0.1, 0.0, 0.9, 0.8])
- Contrast Treatment: 20px blur backdrop-filter overlay with dark-mode tint
- Type Scale: Strict Major Third (1.250), Display font letter-spacing: -0.05em
- Motion Layer: Physics-based GSAP ScrollTrigger with custom cubic-bezier curves
- Badges: Awwwards Site of the Day ribbon at top-right

TASK:
Analyze the structural tension between the typographic grid and the organic focal subject.
Derive the exact design rule this site uses to achieve visual prestige without using filler adjectives.
```

### The Rule of Thumb

- If it has an exact numerical value (color, spacing, font, blur, DOM nodes, motion duration), **measure it with code**.
- If it is a visible physical object (face, 3D model, ribbon, illustration), **isolate it with a single-image VLM**.
- If it is an analytical conclusion (the "Taste Rule"), **synthesize it with an LLM using the metrics generated above**.

---

### Addendum: Closing the Remaining Gaps (The 3 Missing Pillars)

While the decoupled architecture above correctly separates measurement from visual grounding, a truly complete Foundation Model dataset requires three additional refinements:

#### 1. Spatial Topology (The "Grid" Gap)
**The Problem:** Extracting computed CSS (like `fontSize: 120px` or `backdropFilter`) per element is insufficient if the model does not know *where* that element sits. Premium design is defined by layout tension, grid-breaking, and whitespace mass.
**The Solution:** Stage 1 (Headless Browser) must also extract the normalized bounding box `(x, y, width, height)` and `z-index` for every text node, image, and section. This converts the DOM into a mathematical grid.

#### 2. The "Motion Disconnect" (The Temporal Gap)
**The Problem:** Feeding the VLM one static frame isolates objects but destroys the essence of *motion* (delta over time). While Stage 1 extracts CSS easing math, the text model won't know *what* moved (e.g., "typography skews on scroll").
**The Solution:** Introduce **Stage 2.5 (Motion Delta)**. Feed the VLM a two-frame composite (Hero Frame vs. End Scroll Frame) and ask a strict question: *"JSON array of objects that changed position, scale, or opacity."*

#### 3. Negative Baselines (The Synthesis Gap)
**The Problem:** In Stage 3, if you ask the LLM to deduce the "Taste Rule" from only Awwwards sites, it lacks a frame of reference for generic design. It cannot define "prestige" in a vacuum.
**The Solution:** The Stage 3 Synthesizer prompt must require a synthetic contrast. Force the LLM to contrast the extracted metrics (e.g., *1.333 typography scale with -0.05em tracking*) against a standard Bootstrap 5 default implementation.
