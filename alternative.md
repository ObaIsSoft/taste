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

**The Problem:** Extracting computed CSS (like `fontSize: 120px` or `backdropFilter`) per element is insufficient if the model does not know _where_ that element sits. Premium design is defined by layout tension, grid-breaking, and whitespace mass.
**The Solution:** Stage 1 (Headless Browser) must also extract the normalized bounding box `(x, y, width, height)` and `z-index` for every text node, image, and section. This converts the DOM into a mathematical grid.

#### 2. The "Motion Disconnect" (The Temporal Gap)

**The Problem:** Feeding the VLM one static frame isolates objects but destroys the essence of _motion_ (delta over time). While Stage 1 extracts CSS easing math, the text model won't know _what_ moved (e.g., "typography skews on scroll").
**The Solution:** Introduce **Stage 2.5 (Motion Delta)**. Feed the VLM a two-frame composite (Hero Frame vs. End Scroll Frame) and ask a strict question: _"JSON array of objects that changed position, scale, or opacity."_

#### 3. Negative Baselines (The Synthesis Gap)

**The Problem:** In Stage 3, if you ask the LLM to deduce the "Taste Rule" from only Awwwards sites, it lacks a frame of reference for generic design. It cannot define "prestige" in a vacuum.
**The Solution:** The Stage 3 Synthesizer prompt must require a synthetic contrast. Force the LLM to contrast the extracted metrics (e.g., _1.333 typography scale with -0.05em tracking_) against a standard Bootstrap 5 default implementation.

Pivoting away from code generation to an **Aesthetic Reward Model and Design Critic** directly targets the primary bottleneck in contemporary AI interface design. Generative code tools (v0, Bolt, Lovable, Claude Artifacts) are already commoditized; their core failure mode is not syntax, but an acute **taste deficit**—they default to generic, median Tailwind and Bootstrap patterns because their training data is dominated by average web conventions.

Building an aesthetic critic positions your model as the **governing layer** over any generative agent, design tool (Figma), or LLM ecosystem via the Model Context Protocol (MCP).

---

### The Paradigm: The Critic as an Optimization Function

In design, evaluation is fundamentally higher leverage than generation. If an AI can reliably differentiate between mediocrity and elite execution, it can act as:

1. **A Continuous Reward Function:** Scoring layouts to select the highest-taste candidates among dozens of generated permutations.
2. **An Elevation Engine:** Quantifying the exact mathematical distance between a current design and an award-winning layout, then prescribing precise parametric adjustments.
3. **An Uncompromising Design Director via MCP:** Plugging directly into Claude or Cursor to intercept and refine UI proposals before code is written.

```
┌────────────────────────────────────────────────────────┐
│ Generative Agent (e.g., Claude, Cursor, v0)           │
└──────────────────────────┬─────────────────────────────┘
                           │ 1. Proposes Layout / Tokens
                           ▼
┌────────────────────────────────────────────────────────┐
│ TASTE ENGINE (Path B: Critic / Reward Model via MCP)   │
│ - Calculates TrueSkill-calibrated aesthetic score      │
│ - Identifies structural failure modes                  │
│ - Emits Parametric Elevation Directives                │
└──────────────────────────┬─────────────────────────────┘
                           │ 2. Guided Elevation Loop
                           ▼
┌────────────────────────────────────────────────────────┐
│ Elevated Production Artifact (Figma Node / Web Canvas) │
└────────────────────────────────────────────────────────┘

```

---

### Training Formulation: The Direct Preference Critic (DPO)

For a critic, standard supervised fine-tuning (SFT) is insufficient because it teaches the model what to say, but not what to reject. Direct Preference Optimization (DPO) directly aligns the critic's output distribution with your TrueSkill voting data.

#### The DPO Data Tuple $(x, y_w, y_l)$

- **Input Context ($x$):** The extracted design metrics of a site (DOM depth, typography scale, whitespace ratio, motion easing).
- **Chosen Critique ($y_w$):** The high-tier aesthetic critique derived from the Top 15 cohort. It speaks in verified geometric and kinetic facts, identifying structural tension, baseline contrast, and spatial hierarchy.
- **Rejected Critique ($y_l$):** Either the baseline analysis from the Bottom 15 cohort or a synthetic generic critique filled with low-information buzzwords (_"Looks clean and modern, good use of white space"_).

$$\mathcal{L}_{\text{DPO}}(\pi_\theta; \pi_{\text{ref}}) = - \mathbb{E}_{(x, y_w, y_l)} \left[ \log \sigma \left( \beta \log \frac{\pi_\theta(y_w\vert{}x)}{\pi_{\text{ref}}(y_w\vert{}x)} - \beta \log \frac{\pi_\theta(y_l\vert{}x)}{\pi_{\text{ref}}(y_l\vert{}x)} \right) \right]$$

By minimizing this loss, the model actively suppresses generic design clichés and optimizes for forensic, parametric design auditing.

---

### Exposing the Model as an MCP Server for Claude

The Model Context Protocol (MCP) allows Claude Desktop or agentic workflows to call your fine-tuned model as an external expert system. You define three core tool primitives:

#### 1. `audit_aesthetic_equilibrium`

- **Input:** Raw design metrics or screenshot metadata.
- **Task:** Outputs a conservative aesthetic rating $R = \mu - 3\sigma$ calibrated against your TrueSkill dataset and classifies the site into an aesthetic archetype (e.g., _Kinetic Brutalism_, _Monochrome Minimal_, _Commodity SaaS_).

#### 2. `prescribe_elevation_vector`

- **Input:** The design tokens of an inferior or mediocre layout.
- **Task:** Calculates the delta between the input and the closest high-$\mu$ vector in your Supabase database.
- **Output:** Exact directional shifts:

```json
{
  "current_mu_estimate": 18.4,
  "target_archetype": "Architectural Monochrome",
  "elevation_directives": [
    {
      "property": "type_scale",
      "current": 1.15,
      "recommended": 1.333,
      "rationale": "Expand typographic contrast to establish clear visual anchors."
    },
    {
      "property": "whitespace_ratio",
      "current": "22%",
      "recommended": "46%",
      "rationale": "Isolate the primary message by stripping component-level borders and expanding vertical rhythm."
    }
  ]
}
```

#### 3. `evaluate_pairwise_variants`

- **Input:** Metrics from Variant A vs. Variant B.
- **Task:** Predicts the Bradley-Terry preference probability:

$$P(A > B) = \frac{1}{1 + 10^{(\mu_B - \mu_A) / 400}}$$

Explaining precisely which structural decisions give one variant the competitive advantage.

---

### Dataset Construction for the Critic

To train this critic using Unsloth on your Kaggle environment, compile your Supabase voting database into preference pairs formatted for DPO:

```json
{
  "prompt": "Analyze the aesthetic hierarchy and spatial execution of the provided layout configuration:\n- Whitespace: 19%\n- Display Tracking: 0.0em\n- DOM Depth: 24\n- Surface: Solid borders, box-shadow elevation",
  "chosen": "The layout suffers from component saturation. It relies on decorative containment (borders and shadows) rather than spatial discipline. To elevate this into high aesthetic standing: eliminate secondary border containers, increase viewport whitespace to >40%, and compress the display letter-spacing to -0.04em to create typographic density against negative space.",
  "rejected": "The design looks clean and functional. The buttons are clearly laid out with nice shadows, making it very user-friendly. Just make the text a bit bigger and keep the colors modern."
}
```

This training transforms an open-weight base model (like Qwen 2.5 7B) into an uncompromising design critic that can inspect a design, calculate its aesthetic shortcomings, and supply the missing taste layer to any human or AI designer.

Research in computational aesthetics, human-computer interaction (HCI), and automated layout generation has explored adjacent territory for over two decades. However, almost no one has built your **exact integrated loop**—scraping runtime animation physics, applying Bayesian pairwise preference modeling to elite design, and training a DPO-based aesthetic reward model/critic.

The absence of this exact system is the result of deep historical biases in academic research, severe engineering barriers in web data extraction, and a commercial fixation on code generation over design evaluation.

---

### 1. What Prior Research Actually Did

Prior academic and industrial research tackled fragments of this problem, but always stopped short of quantifying elite taste.

- **Computational Web Aesthetics (Early HCI):**
  Between 2007 and 2015, researchers like Katharina Reinecke (_Predicting Users' First Impressions of Website Visual Aesthetics_, CHI 2014) and Miniukovich & De Angeli (_Computation of Interface Aesthetics_, CHI 2015) attempted to quantify visual appeal. They used hand-crafted, low-level vision heuristics: visual clutter, symmetry, color harmony, and whitespace ratios.
- _The Limitation:_ Their mathematical models were static regression equations. They evaluated generic, early-2010s corporate and informational websites, completely missing modern kinetic, typographic, and spatial systems.

- **Large-Scale UI Datasets (Rico, WebUI, Clay):**
  Datasets like _Rico_ (66,000+ mobile screens) and Google's _WebUI_ (400,000+ web pages) mined layouts at scale.
- _The Limitation:_ They were engineered for **functional parsing**, not aesthetics. They mapped bounding boxes so models could learn OCR, predict button clicks, or automate accessibility labels. None of them filtered for visual prestige or scraped animation timelines.

- **Aesthetic Quality Assessment (NIMA, AVA Dataset):**
  Computer vision has mature models for photographic aesthetic scoring (e.g., Google’s NIMA: _Neural Image Assessment_).
- _The Limitation:_ These models are trained entirely on photographs (lighting, depth of field, rule of thirds). When applied to UI/UX, they fail completely because they do not understand typographic hierarchy, DOM semantics, layout tension, or dynamic interaction.

- **Generative Layout Models (LayoutGAN, Design2Code, v0):**
  Recent work focuses on transforming wireframes into HTML/CSS or generating layouts from text prompts.
- _The Limitation:_ These are unconditional or conditional generative systems. They treat web generation as a translation problem ($P(\text{Code} \mid \text{Image})$), operating with zero internal concept of aesthetic evaluation ($P(\text{Quality} \mid \text{Design})$).

---

### 2. The 5 Reasons No One Has Built This Exact System

#### Reason 1: The Academic Usability Dogma

In academic HCI, "good design" has historically been defined strictly by **usability, accessibility, and utility** (e.g., Jakob Nielsen’s heuristics, Fitts's Law, WCAG compliance, task-completion speed).

Within that paradigm, Awwwards-style websites are often dismissed as "anti-patterns":

- They hijack native scroll physics.
- They use unconventional navigation.
- They intentionally sacrifice immediate readability for atmospheric mood, brand prestige, and spatial tension.

Because computer science departments evaluate interfaces through quantitative user studies (e.g., "Did the user find the checkout button in under 3 seconds?"), the industry of _elite visual taste_ was largely ignored by academic research as unscientific or superficial marketing.

#### Reason 2: The Crowdsourcing Trap (Regression to the Mean)

When researchers previously attempted to collect aesthetic datasets, they turned to Amazon Mechanical Turk or Prolific, presenting random users with Likert scales (_"Rate this site from 1 to 5 stars"_).

This approach destroys taste data:

- **The Median Voter Bias:** The average person prefers familiar, safe, low-cognitive-friction interfaces (standard SaaS, Bootstrap, Amazon-like layouts).
- **Aesthetic Flattening:** Avant-garde typography, radical negative space, and dark-mode brutalism receive polarized scores (1s from non-designers, 5s from creative directors). Aggregating them yields a mediocre score of 2.5.
- **The Pairwise Fix:** Your use of **pairwise TrueSkill with Cosine-Similarity vibe matching** prevents this regression. You do not ask "Is this site a 5?"; you ask "Between these two dark-mode brutalist sites, which one executes its spatial hierarchy better?" Most researchers never implemented this matchmaking layer.

#### Reason 3: The Dynamic Runtime Scraping Barrier

Mining standard HTML is trivial. Mining modern tier-1 WebGL/GSAP websites is an engineering nightmare:

- Standard scrapers (BeautifulSoup, Scrapy, basic Selenium) only see the initial raw HTML payload.
- Award-winning sites construct their DOM dynamically via client-side hydration, render graphics inside WebGL canvases, and register scroll logic via memory closures (`requestAnimationFrame`, Lenis, Locomotive).
- Capturing structural truth requires the complex browser instrumentation you had to build: injecting prototype hooks to intercept `gsap.to`, simulating physical native mouse coordinates to penetrate full-screen canvases, and recording video streams to extract layout shifts via keyframe MSE. Most machine learning researchers do not have the front-end engineering expertise to build runtime JavaScript interception hooks.

#### Reason 4: The Commercial "Generative Code" Gold Rush

Between 2023 and 2026, venture capital and commercial AI startups poured hundreds of millions of dollars into **generative coding** (v0, Bolt, Lovable, Cursor, Devin).

The industry operated on an engineering assumption: _"If we give an LLM enough React/Tailwind training data, it will build great software."_

This ignored Goodhart's Law. Current generative models produce functionally working code that is aesthetically generic. They hit an aesthetic ceiling because they are trained on common internet crawl data (the average of GitHub and the web). The realization that **we need an external, non-generative Reward Model / Aesthetic Critic** to steer these generators is only now emerging as developers grow fatigued by identical-looking AI interfaces.

#### Reason 5: The Recency of Direct Preference Optimization (DPO)

Before the publication of DPO (Rafailov et al., late 2023) and its optimization in frameworks like Unsloth, aligning a model to preferences required Reinforcement Learning from Human Feedback via PPO (Proximal Policy Optimization).

PPO requires training four separate neural networks simultaneously (the policy, value model, reward model, and reference model). It is computationally fragile, hyper-parameter sensitive, and virtually impossible to run on small parameter footprints or limited GPU compute. DPO reduced preference optimization to a single, stable cross-entropy loss over paired tokens $(x, y_w, y_l)$. The mathematical tooling to build a lightweight, fine-tuned preference critic simply did not exist in an accessible form until recently.

---

### 3. Your Research Contribution

By building this, you are effectively challenging the assumption that visual taste is an indefinable human intuition.

Your paper/system represents three genuine contributions to computational design:

1. **Instrumentation:** Proving that interaction aesthetics and motion choreography can be extracted directly from browser memory (intercepting GSAP/DOM deltas) rather than guessing from static screenshots.
2. **Bayesian Preference Architecture:** Demonstrating that TrueSkill paired with latent-vector vibe matching stabilizes aesthetic ground truth with an order of magnitude fewer evaluations than unconstrained voting.
3. **The Critic Paradigm:** Framing aesthetic AI not as an unguided code generator, but as a calibrated **Reward Model / Elevation Vector** that can be injected into any agentic loop via MCP.

What specific base model do you plan to train as your critic—a pure text model like Qwen 2.5 7B fed with extracted metrics, or a multimodal vision-language model like Qwen2-VL?
