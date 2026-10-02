# TASTE Engine v2: Design Document

**Date:** September 28, 2026
**Status:** Draft — pending voter pilot
**Author:** obafemi + AI

---

## 1. Executive Summary

### What's changing

| Layer | v1 (current) | v2 (proposed) | Why |
|---|---|---|---|
| **Labels** | VLM-confabulated rationales | Human voter reasoning | VLM claims GSAP at sites with zero GSAP detection |
| **Voters** | 1 (unknown count) | 3–5 designers | Single-voter TrueSkill is one person's taste, not ground truth |
| **Images** | 2 screenshots + 0–37 keyframes + video | 2 screenshots only | Video pipeline is expensive; keyframes mostly discarded |
| **VLM role** | Label generator (taste_rationale.json) | Feature extractor (stage2_vlm_raw.json) | VLM describes what it sees; humans decide what's good |
| **Model** | Single-stage LLM (failed at 49%) | MDPD: multi-dimensional preference decomposition | DPO assumes transitivity; taste violates it by design — gradients cancel, model guesses |
| **Metrics** | Broken (asymmetry has no variance) | DOM-based, validated against votes | Current metrics don't capture what voters respond to |

### Why

The 461-pair pilot produced 49% accuracy — a coin flip. The diagnosis was overfitting, but the root cause is the data pipeline:

1. **Labels are confabulated.** VLM rationales describe motion that doesn't exist in the extracted code. The `negative_baseline` field is 100% templated ("Unlike Bootstrap 5..."). Training on confabulated labels teaches the model to confabulate.

2. **Ground truth is one person.** 620+ votes from an unknown number of voters (likely 1). No inter-rater agreement measurement exists. TrueSkill with n=1 produces one person's preferences with Bayesian confidence intervals.

3. **Metrics are broken.** `asymmetry_score` (luminance center-of-mass) scores 0.001–0.25 across all 100 sites — no variance, no signal. The metrics don't capture the features voters actually respond to.

4. **The pipeline is too expensive.** Video recording → keyframe extraction → VLM analysis per site. The keyframes (0–37 per site) were only used for VLM rationale generation, which is being replaced by voter reasoning.

---

## 2. The New Architecture

### 2.1 Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STAGE 0: COLLECTION                          │
│  scraper.py → 2 screenshots + DOM metadata + motion code (no video) │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    STAGE 1: VLM FEATURE EXTRACTION                 │
│  VLM analyzes hero screenshot → structured features                │
│  (focal_subject, background_style, badges, whitespace_distribution) │
│  These are FEATURES (input context), NOT labels (DPO targets)       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    STAGE 2: MULTI-VOTER VOTING                     │
│  3–5 designers vote on pairs (A vs B) with reasoning box           │
│  "What specific features made A better than B?"                     │
│  Voter ID + reasoning stored in Supabase                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                    STAGE 3: METRICS VALIDATION                      │
│  Measure which features predict vote outcomes                      │
│  Identify residual votes (metrics equal, preference clear)          │
│  Compute transitivity index (voter consistency)                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│              STAGE 4: MDPD MODEL (Multi-Dimensional                 │
│                  Preference Decomposition)                          │
│                                                                     │
│  Input: metrics for A and B (14 continuous values)                  │
│  ↓                                                                  │
│  Shared Encoder (Transformer)                                      │
│  ↓                                                                  │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐               │
│  │ Head 1  │ Head 2  │ Head 3  │  ...    │ Head N  │               │
│  │whitespace│typography│ color  │         │ semantic│               │
│  └────┬────┴────┬────┴────┬────┴─────────┴────┬────┘               │
│       │         │         │                   │                     │
│       └─────────┴────┬────┴───────────────────┘                     │
│                      ▼                                              │
│  Aggregator (learns dimensional weights per context)                │
│  ↓                                                                  │
│  P(A wins) = Σᵢ wᵢ · P(A wins on dimᵢ)                            │
│                                                                     │
│  Loss: sparse — only cited dimensions get gradient                  │
│  (voter reasoning → dimension mask → head activation)              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│              STAGE 5: RESIDUAL VISION MODEL                         │
│  residual = actual_vote − MDPD_prediction                          │
│  Vision model learns the residual from screenshots                  │
│  (the "taste" that metrics can't capture)                          │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Stage 0: Collection (Scraper)

**What changes:**
- Remove video recording entirely
- Remove keyframe extraction from the scraping pipeline
- Keep 2 screenshots: hero (above fold) and full page
- Keep DOM metadata (computed styles with bboxes) — this is the richest data source
- Keep motion code extraction (with fixes)
- Add `scrollTo(0, 0)` before hero screenshot (scroll-restoration can offset the hero)
- Neutralize Locomotive/Lenis before full-page capture

**What's removed:**
- `record_video` parameter and `.webm` recording
- `preprocess_video.py` call from the pipeline
- `motion_storyboard.json` generation
- `frames/` directory creation

**Why:** Video processing is expensive (90s recording + MSE keyframe extraction per site) and the keyframes were only used for VLM rationale generation, which is being replaced. The 2 screenshots are sufficient for the vision model (stage 2).

### 2.3 Stage 1: VLM Feature Extraction (Batch, Optional)

**What changes:**
- VLM analyzes the hero screenshot → structured JSON features
- Output: `stage2_vlm_raw.json` (focal_subject, background_style, badges, whitespace_distribution)
- These features are **input context** for the DPO prompt, not labels
- Can be run in batch after scraping, not during

**What's removed:**
- `taste_rationale.json` generation during enrichment
- The gemma4 synthesizer step (or repurposed for batch use only)

**Why:** The VLM is good at describing what it sees (focal subject, background style) but bad at explaining why a design is good. Let it do what it's good at — feature extraction — and let humans do what they're good at — judgment.

### 2.4 Stage 2: Multi-Voter Voting

**What changes:**
- 3–5 designers vote on pairs
- Each vote includes: voter_id, winner, reasoning (free-text)
- Reasoning prompt: *"What specific features made [A/B] better?"*
- Voter reliability tracked (running agreement with consensus)
- Votes stored in Supabase `match_history` table (extended with `voter_id`, `reasoning`)

**Why:** Human reasoning tied to an actual vote is the ground truth the DPO labels need. The reasoning explains *why* A beat B, which is exactly what the `chosen` field should contain.

### 2.5 Stage 3: Metrics Validation

**What changes:**
- Measure which features predict vote outcomes (feature win rates)
- Identify residual votes (metrics equal, preference clear)
- Compute transitivity index (voter consistency)
- Use residual to guide metric development

**Why:** The current metrics are assumed to matter. They should be *validated* against vote outcomes. If whitespace predicts the vote 80% of the time, it's causal. If it predicts 50%, it's noise.

### 2.6 Stage 4: MDPD Model (Multi-Dimensional Preference Decomposition)

**The core insight:** DPO failed because it assumes taste is a scalar preference (A > B > C). Taste is not scalar — it's a **high-dimensional vector field**. A beats B on whitespace, B beats C on typography, C beats A on color. When you feed cyclic preferences into DPO, the gradients cancel and the model learns to guess (49% accuracy).

**The fix:** decompose the preference into dimensions. Each dimension is a clean, transitive sub-problem. The model learns which dimensions matter for which design category.

**Architecture:**
- **Shared encoder:** processes both designs' metrics simultaneously
- **N heads (one per dimension):** each head predicts which design wins on its dimension
- **Aggregator:** learns how to weight dimensions based on design category and voter profile
- **Sparse masking:** only the dimensions cited in the voter's reasoning get a gradient

**The dimensions are discovered, not assumed.** The current 7 (whitespace, typography, color, motion, composition, texture, semantic) are hypotheses. The calibration phase and factor analysis on vote patterns will reveal the actual latent dimensions. The model might find 5, or 9. Build the heads after discovering the dimensions.

**Training protocol:**
1. Train each head independently on only the votes that cite its dimension (sparse head activation — prevents gradient interference)
2. Train the aggregator to learn contextual weights (brutalism weights whitespace heavily; editorial weights typography heavily)
3. The residual vision model learns what the metrics can't explain

**Why this works when DPO failed:**
- Each head learns a clean, transitive sub-problem (whitespace is mostly ordinal)
- Cycles are not noise — they're dimensional trade-offs the model learns to represent
- The loser may be better on uncited dimensions — no penalty (unlike DPO)
- Multiple voters = multiple valid taste profiles (not a single ground truth)

### 2.7 Stage 5: Residual Vision Model

**What it is:** a separate model that learns the **residual** — the preference variance that the MDPD model cannot explain from metrics alone.

```
residual = actual_vote − MDPD_prediction
```

If the MDPD model says "50/50" (equal on all dimensions) but voters prefer A 80% of the time, the vision model learns to detect the visual feature that explains the 30% gap. This might be texture, micro-typography, image quality, or the "uncanny valley" of almost-right-but-slightly-off.

**Why separate:** the metrics explain the measurable part of taste; the vision model explains the immeasurable part. Together they capture both. The vision model doesn't learn taste from scratch — it learns only the correction.

### 2.8 Voter Guide

A README at `taste-engine/web/README.md` guides designers through the voting process:
- How voting works (pairwise comparison, A vs B)
- The rules (vote on aesthetic quality, not personal preference)
- What to keep in mind (the 7 dimensions as questions to ask)
- How to write reasoning (specific, feature-citing, comparative — with examples)
- Time commitment (~30–60 seconds per vote, ~50 votes)
- FAQ

The guide is written for designers who may not know anything about the project. It should take 2 minutes to read and answer every question a voter might have.

---

## 3. Data Strategy

### 3.1 Per-site data (v1 vs v2)

| Data | v1 | v2 | Why |
|---|---|---|---|
| `screenshot_hero.png` | ✓ | ✓ | Primary visual for taste model |
| `screenshot_full.png` | ✓ | ✓ | Full page context |
| `frames/` (0–37 jpgs) | ✓ | ✗ | Video-derived, expensive, mostly discarded |
| `page@*.webm` | ✓ | ✗ | Video processing is expensive; keyframes were the useful part |
| `metadata.json` | ✓ | ✓ | Richest data source (DOM computed styles with bboxes) |
| `visual_analysis.json` | ✓ | ✓ (fixed) | Replace asymmetry, add quadrant distribution |
| `motion_code.json` | ✓ | ✓ (fixed) | GSAP extraction is broken; needs async fix |
| `motion_storyboard.json` | ✓ | ✗ | Only needed for frames |
| `stage2_vlm_raw.json` | ✓ | ✓ (repurposed) | Feature extractor, not label generator |
| `taste_rationale.json` | ✓ | ✗ (replaced) | VLM confabulation → voter reasoning |
| `embedding.json` | ✓ | ✓ (regenerated) | From voter reasoning, not VLM rationale |

### 3.2 Image strategy

**2 images per site:**
1. `screenshot_hero.png` — above-the-fold, taken before any scrolling
2. `screenshot_full.png` — full page, taken after neutralizing scroll libraries

**No video recording.** No keyframe extraction. No `frames/` directory.

**Why:** The video pipeline (90s recording + MSE keyframe extraction) was expensive and the keyframes were only used for VLM rationale generation. The 2 screenshots are sufficient for the vision model (stage 2 of the two-stage architecture). If the taste model needs more visual context later, we can add targeted screenshots (e.g., mid-scroll) without the full video pipeline.

### 3.3 VLM reasoning changes

**v1 (current):**
```
screenshot → VLM forensic analysis → gemma4 synthesizer → taste_rationale.json
```
The VLM rationale is the DPO label. It's confabulated.

**v2 (proposed):**
```
screenshot → VLM forensic analysis → stage2_vlm_raw.json (FEATURE)
pairwise vote + voter reasoning → DPO label (HUMAN)
```

The VLM is a **feature extractor**, not a **label generator**. It describes what it sees (focal subject, background style, badges, whitespace distribution). Humans decide what's good.

**Why:** The VLM can't explain why a design is good — it can only describe what's there. The gemma4 synthesizer then confabulates plausible-sounding explanations that don't match the detected motion code. Human reasoning tied to an actual vote is the ground truth.

---

## 4. Task List

### Workstream 1: Multi-Voter System (web app + API)

- [ ] **T1.1** — Add voter ID field to voting UI (name or identifier)
- [ ] **T1.2** — Add reasoning text box with prompt: *"What specific features made [A/B] better?"*
- [ ] **T1.3** — Make reasoning required (or strongly encouraged with minimum length)
- [ ] **T1.4** — Extend Supabase `match_history` table: add `voter_id`, `reasoning` columns
- [ ] **T1.5** — Update `/api/vote` to accept and persist `voter_id` + `reasoning`
- [ ] **T1.6** — Update `index.html` voting flow to capture reasoning before submitting
- [ ] **T1.7** — Add voter reliability scoring (running agreement with consensus)
- [ ] **T1.8** — Show voters their own agreement stats (motivates quality)
- [ ] **T1.9** — Add voter onboarding: explain the 5 comparison criteria, show examples

### Workstream 2: Scraper Fixes

- [ ] **T2.1** — Remove video recording from `scraper.py` (delete `record_video` param, `.webm` recording)
- [ ] **T2.2** — Remove keyframe extraction from pipeline (delete `preprocess_video.py` call)
- [ ] **T2.3** — Add `window.scrollTo(0, 0)` before hero screenshot in `scraper.py`
- [ ] **T2.4** — Fix GSAP async loading: poll for `window.gsap` and re-install interceptor when it lands
- [ ] **T2.5** — Fix GSAP module-bundled detection: regex JS source for `gsap.to(` patterns
- [ ] **T2.6** — Fix click-through: measure bounding box and click in same frame; add CDP fallback
- [ ] **T2.7** — Fix full-page screenshot: neutralize Locomotive/Lenis before `full_page=True` capture
- [ ] **T2.8** — Add retry logic for failed extractions (GSAP, motion, screenshots)
- [ ] **T2.9** — Remove `motion_storyboard.json` and `frames/` generation from pipeline

### Workstream 3: Metrics Fixes

- [ ] **T3.1** — Replace `asymmetry_score` with DOM-based layout imbalance (area-weighted left/right mass from `computed_styles` bboxes)
- [ ] **T3.2** — Add 3×3 quadrant distribution (spatial signature: "top-left heavy" vs "centered" vs "diagonal")
- [ ] **T3.3** — Validate `whitespace_ratio` (distinguish intentional void from blank loading screen)
- [ ] **T3.4** — Add more DOM features: font size variance, letter-spacing range, z-index depth, color count, section count
- [ ] **T3.5** — Write `scripts/metrics_validation.py`: measure which features predict vote outcomes
- [ ] **T3.6** — Write `scripts/transitivity_index.py`: measure voter consistency
- [ ] **T3.7** — Write `scripts/residual_detector.py`: identify votes where metrics are equal but preference is clear

### Workstream 4: Rationale Pipeline

- [ ] **T4.1** — Add validation gate: check every claimed feature in rationale against `motion_code.json` and `visual_analysis.json`
- [ ] **T4.2** — Constrain synthesizer prompt: "Cite ONLY features present in the metric sheet"
- [ ] **T4.3** — Repurpose `stage2_vlm_raw.json` as feature (input context), not label
- [ ] **T4.4** — Remove `taste_rationale.json` generation from `enrich.py` (or make it batch-only)
- [ ] **T4.5** — Regenerate `embedding.json` from voter reasoning (not VLM rationale)

### Workstream 5: DPO Dataset Restructure

- [ ] **T5.1** — Write `scripts/dpo_from_votes.py`: compile DPO tuples from voter reasoning
- [ ] **T5.2** — New tuple structure: `chosen` = voter reasoning, `rejected` = same reasoning with verdict flipped
- [ ] **T5.3** — Use voter agreement with consensus as MADPO margin (or combine with TrueSkill margin)
- [ ] **T5.4** — Tag residual votes (metrics equal, preference clear) — these are the most valuable
- [ ] **T5.5** — Re-compile the 461 pairs with voter reasoning instead of VLM rationales
- [ ] **T5.6** — Handle abstentions: if voter skips or says "no preference," record as draw

### Workstream 6: Multi-Voter Ground Truth

- [ ] **T6.1** — Recruit 3–5 designers (activate the "designer network" from the brief)
- [ ] **T6.2** — Run pilot study: 50–100 pairs, all voters vote on all pairs
- [ ] **T6.3** — Measure inter-rater agreement: Fleiss' κ or Krippendorff's α
- [ ] **T6.4** — If κ < 0.4: voting criteria too vague — refine prompt, add examples, retrain voters
- [ ] **T6.5** — If κ > 0.6: proceed to full 10k vote collection
- [ ] **T6.6** — Weight votes by voter reliability (voters who agree with consensus more often get higher weight)

### Workstream 7: Scaling Infrastructure

- [ ] **T7.1** — Apply scraper fixes (Workstream 2) to `batch_scraper_v2.py`
- [ ] **T7.2** — Add anti-bot handling: `playwright-stealth` or residential proxies (site-086 showed bot-block)
- [ ] **T7.3** — Plan storage: 100 sites = 1.4 GB → 1000 sites ≈ 14 GB (Git LFS or object storage)
- [ ] **T7.4** — Parallelize voting: Supabase already supports simultaneous voters (no change needed)
- [ ] **T7.5** — Add progress tracking dashboard: votes collected, per-voter progress, inter-rater agreement

### Workstream 8: MDPD Model

- [ ] **T8.1** — Replace mocked VLM scalars in `prepare_nano_dataset.py` with real values from `batch_scraper_v2.py`
- [ ] **T8.2** — Re-run overfit sandbox with real features (not `random.uniform`)
- [ ] **T8.3** — Discover latent dimensions: run factor analysis on vote patterns, don't assume 7
- [ ] **T8.4** — Build dimension extractor: `reasoning → [dimensions]` with confidence scores (keyword + LLM classifier)
- [ ] **T8.5** — Build MDPD nano-transformer: N heads (one per discovered dimension), sparse masking from dimension extractor
- [ ] **T8.6** — Train heads independently on their relevant vote subsets (sparse head activation)
- [ ] **T8.7** — Train aggregator: learn contextual dimensional weights from voter profiles and design categories
- [ ] **T8.8** — Build residual vision model: learns `actual_vote − MDPD_prediction` from screenshots
- [ ] **T8.9** — Validate on held-out pairs before declaring the architecture viable

---

## 5. Code Changes by File

### 5.1 `taste-engine/scripts/scraper.py`

| Change | Why |
|---|---|
| Remove `record_video` param and `.webm` recording | Video pipeline is expensive; keyframes were only for VLM rationale |
| Remove `preprocess_video.py` call | No keyframes needed |
| Add `window.scrollTo(0, 0)` before hero screenshot | Scroll-restoration can offset hero on scroll-hijacked sites |
| Fix GSAP interceptor: poll for async `window.gsap` | Current code does `if (!window.gsap) return` and never retries |
| Add GSAP source regex: `gsap.to(` in JS source | Catches ES module imports that never set `window.gsap` |
| Fix click-through: same-frame measure + click | Bounding box can shift between measurement and click due to parallax |
| Add CDP fallback: `Input.dispatchMouseEvent` | For stubborn gates that don't respond to Playwright clicks |
| Neutralize Locomotive/Lenis before full-page capture | `full_page=True` produces broken stitches on scroll-hijacked sites |
| Remove `motion_storyboard.json` and `frames/` generation | No longer needed |

### 5.2 `taste-engine/scripts/analyzer.py`

| Change | Why |
|---|---|
| Replace `asymmetry_score` with DOM-based layout imbalance | Current luminance center-of-mass has no variance (all sites 0.001–0.25) |
| Add 3×3 quadrant distribution | Captures spatial signature: "top-left heavy" vs "centered" vs "diagonal" |
| Add font size variance, letter-spacing range, z-index depth | More features from existing DOM data |
| Add color count, section count | More features from existing DOM data |

### 5.3 `taste-engine/scripts/enrich.py`

| Change | Why |
|---|---|
| Remove `taste_rationale.json` generation | VLM confabulation → voter reasoning |
| Keep `stage2_vlm_raw.json` as feature extraction | VLM describes what it sees; humans decide what's good |
| Add validation gate: check claimed features against data | Reject rationales that claim undetected features |
| Constrain synthesizer prompt: "cite ONLY detected features" | Prevents confabulation |

### 5.4 `taste-engine/scripts/compile_dpo_dataset.py`

| Change | Why |
|---|---|
| Use voter reasoning as `chosen` | Human reasoning is the ground truth label |
| Derive `rejected` by flipping verdict | Reasoning no longer matches loser's metrics |
| Use voter agreement as MADPO margin | Voter reliability is the confidence signal |
| Tag residual votes | Metrics equal but preference clear — most valuable training data |

### 5.5 `taste-engine/web/api/index.py`

| Change | Why |
|---|---|
| Accept `voter_id` and `reasoning` in `/api/vote` | Store human reasoning with each vote |
| Add voter reliability scoring | Track agreement with consensus |
| Add `/api/voter_stats` endpoint | Show voters their own agreement stats |

### 5.6 `taste-engine/web/public/index.html`

| Change | Why |
|---|---|
| Add voter ID field | Identify who is voting |
| Add reasoning text box | Capture why the voter preferred A or B |
| Update voting flow | Capture reasoning before submitting |
| Add voter onboarding | Explain comparison criteria, show examples |

### 5.7 `taste-engine/scripts/prepare_nano_dataset.py`

| Change | Why |
|---|---|
| Replace `random.uniform(0.1, 1.0)` with real VLM scalars | Mocked features prove nothing |
| Use real `intentionality_score`, `palette_cohesion`, `typographic_hierarchy` from `batch_scraper_v2.py` | The 14-token architecture was "proven" on random data |

### 5.8 New files

| File | Purpose |
|---|---|
| `scripts/metrics_validation.py` | Measure which features predict vote outcomes |
| `scripts/voter_reliability.py` | Track voter agreement with consensus |
| `scripts/transitivity_index.py` | Measure voter consistency (fraction of transitive triples) |
| `scripts/residual_detector.py` | Identify votes where metrics are equal but preference is clear |
| `scripts/dpo_from_votes.py` | Compile DPO tuples from voter reasoning |
| `scripts/two_stage_model.py` | Two-stage prediction: metrics + vision |

---

## 6. The Residual

### 6.1 What it is

When two sites are measurably identical — same whitespace, same typography, same color variance, same DOM depth — but the voter still prefers one, **the difference is the taste**. The residual isn't noise in the measurement; it's the signal the measurement can't capture.

### 6.2 What it's made of

- Visual quality of imagery (cinematic photo vs stock photo, same bbox)
- Micro-typography (-0.04em vs -0.05em tracking, below measurement floor)
- Texture and grain (film grain, paper texture, noise)
- Motion feel (1.2s vs 1.3s ease-out, same easing curve name)
- Composition (how elements relate, not just where they are)
- Semantic content (the actual words, the brand narrative)
- The uncanny valley (something almost right but slightly off)

### 6.3 How to handle it

**Don't discard residual votes — they're the most valuable ones.** A vote where the metrics are equal but the preference is clear is a pure taste signal.

```python
# Tag residual votes
if abs(metrics_a['whitespace'] - metrics_b['whitespace']) < 0.05 and \
   abs(metrics_a['typography_size'] - metrics_b['typography_size']) < 5 and \
   abs(metrics_a['color_variance'] - metrics_b['color_variance']) < 0.1:
    tuple['is_residual'] = True  # metrics can't explain this — pure taste
```

### 6.4 How to use it

The residual is a roadmap for metric development:
- If voters consistently prefer sites with a certain texture → add a texture metric
- If they prefer sites with smoother motion → add a motion smoothness metric
- The residual tells you **where to measure next**

Track feature win rates:
```python
# For each feature, measure how often it predicts the vote
for feature in ['whitespace', 'typography', 'color_variance', 'asymmetry']:
    matches = total = 0
    for vote in votes:
        a_val = get_feature(vote.a, feature)
        b_val = get_feature(vote.b, feature)
        if abs(a_val - b_val) < threshold:
            continue  # skip residual votes
        predicted = vote.a if a_val > b_val else vote.b
        total += 1
        if predicted == vote.winner:
            matches += 1
    print(f"{feature}: {matches}/{total} = {matches/total:.2%}")
```

If whitespace predicts the vote 80% of the time, it's causal. If it predicts 50%, it's noise.

---

## 7. Intransitivity

### 7.1 The problem

Pairwise voting can produce cycles: A > B, B > C, C > A. This is the Condorcet paradox. It's not voter irrationality — it means the sites are **incomparable on a single dimension**.

### 7.2 What it means

A beats B on whitespace, B beats C on typography, C beats A on color discipline. The "logic" isn't ordinal — it's **dimensional**. The cycle exists because you're projecting a multi-dimensional comparison onto a single axis.

### 7.3 How to quantify it

**Transitivity index** — fraction of transitive triples:
- 1.0 = perfectly consistent voters
- > 0.85 = ground truth is solid
- < 0.7 = comparison criteria too vague

**Cycle decomposition** — for each cycle, look at the reasoning:
- If different dimensions are cited → dimensional trade-off (informative)
- If same dimension is cited → genuine noise (voter inconsistency)

**Feature × site matrix** — extract cited dimensions from reasoning:
```
           whitespace  typography  color  grid  motion
site A         4           3          2      5      3
site B         2           4          3      3      4
site C         3           2          5      4      2
```

This explains every cycle: A > B because whitespace (4 > 2), B > C because typography (4 > 2), C > A because color (5 > 2).

### 7.4 How the reasoning box helps

The reasoning box is a **dimensional probe**. When a voter says "A beat B because of whitespace" and "C beat A because of color discipline," they're telling you *which dimension decided each comparison*. You don't need structured ratings to get the dimensional decomposition — you extract it from the reasoning text.

---

## 8. Scaling Plan

### 8.1 The math

- 100 sites → 620 votes → ~12 comparisons per site
- 1000 sites → 10,000 votes → ~10 comparisons per site
- TrueSkill stabilization threshold: ~10–15 comparisons per site

### 8.2 Voter count

| Voters | Votes per voter | Time per voter (30 sec/vote) | Time per voter (90 sec/vote) |
|---|---|---|---|
| 1 | 10,000 | ~83 hours | ~250 hours |
| 3 | ~3,300 | ~28 hours | ~83 hours |
| 5 | ~2,000 | ~17 hours | ~50 hours |

**Recommendation:** 5 voters, ~2,000 votes each, ~50 hours each with the reasoning box. Run in parallel over 4–6 weeks.

### 8.3 Storage

- 100 sites = 1.4 GB → 1000 sites ≈ 14 GB
- Without video: ~0.5 GB per 100 sites → ~5 GB for 1000 sites
- Use Git LFS or object storage for screenshots

### 8.4 Anti-bot

- site-086 showed bot-block ("Automated access not allowed")
- Need `playwright-stealth` or residential proxies for the 900 new sites
- The journal already flagged this: "Scaling to 1,000 URLs will require playwright-stealth or a residential proxy network"

---

## 9. Timeline

### Week 1: Voter pilot + dimension discovery (Workstream 6)
- Recruit 3 designers (not 5 yet — start small)
- Deploy the reasoning box UI (Workstream 1) + voter guide (`web/README.md`)
- Run calibration phase: 20 forced-choice questions per voter (build voter profiles)
- Run 50 pairwise votes with reasoning
- Extract cited dimensions from reasoning (keyword + LLM classifier)
- Run factor analysis on vote patterns → discover actual latent dimensions
- **Output:** the real dimensions, not the assumed 7
- **Gate:** If κ < 0.4, stop and refine criteria

### Week 2 (parallel): Scraper + metrics (Workstreams 2 + 3)
- Apply scraper fixes (GSAP async, click-through, full-page)
- Implement DOM-based asymmetry
- Write metrics validation scripts
- Re-scrape a test batch of 10 sites with fixed scraper

### Week 3: Dimension extractor + DPO (Workstreams 4 + 5)
- Build dimension extractor: `reasoning → [dimensions]` with confidence scores
- Add validation gate to rationale pipeline
- Write `dpo_from_votes.py`
- Re-compile 461 pairs with voter reasoning
- Tag residual votes

### Week 4: MDPD model (Workstream 8)
- Replace mocked VLM scalars with real ones
- Build MDPD nano-transformer: N heads (one per discovered dimension), sparse masking
- Train heads independently on their relevant vote subsets
- Train aggregator: learn contextual dimensional weights
- Validate on held-out pairs

### Week 5: Residual vision model (Workstream 8)
- Train on residual (actual vote − MDPD prediction)
- Validate on held-out pairs
- If residual model doesn't improve over MDPD alone, the visual signal is noise — accept and move on

### Week 6+: Scaling (Workstream 7)
- Apply scraper fixes to `batch_scraper_v2.py`
- Add anti-bot handling
- Begin 900-site scrape
- Begin full 10k vote collection

---

## 10. Success Criteria

| Metric | Target | Measurement |
|---|---|---|
| Inter-rater agreement (Fleiss' κ) | > 0.6 | Pilot study |
| Transitivity index | > 0.85 | Voting data |
| Feature win rate (whitespace) | > 0.70 | Metrics validation |
| Feature win rate (typography) | > 0.70 | Metrics validation |
| MDPD accuracy (held-out) | > 0.65 | 461-pair test |
| Dimension extraction accuracy | > 0.80 | Held-out reasoning labels |
| Residual vote rate | < 30% | DPO dataset |
| Scraper success rate | > 95% | 900-site batch |
| GSAP extraction rate | > 50% | Motion code audit |

---

## 11. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Voters disagree (κ < 0.4) | Medium | Refine criteria, add examples, more voter training |
| Voter fatigue / dropout | Medium | Keep reasoning short, show progress stats, gamify |
| Anti-bot blocks scaling | High | `playwright-stealth`, residential proxies, rate limiting |
| Residual rate too high (> 50%) | Medium | Add finer-grained metrics, accept that taste is partly immeasurable |
| Two-stage model doesn't improve over single-stage | Medium | The residual is real by definition; the question is whether it's learnable from visuals |
| Reasoning quality varies widely | High | Voter reliability weighting, minimum length requirements, examples |
| Dimensions don't emerge cleanly | Medium | Fall back to the 7 hypothesized dimensions; they're plausible even if not discovered |
| Keyword extraction misses reasoning | Medium | Use LLM classifier with confidence threshold; leave uncertain cases untagged |

---

## 12. Progress Tracker

### Completed

| Task | Date | Notes |
|---|---|---|
| Design doc created | Sep 28 | `TASTE_ENGINE_V2_DESIGN.md` |
| Voter guide created | Sep 28 | `web/public/guide.html` — rules, dimensions, reasoning examples |
| Supabase schema updated | Sep 28 | `voter_id` + `reasoning` columns in `match_history`; new `voters` table |
| API updated | Sep 28 | `/api/vote` accepts `voter_id` + `reasoning`; `/api/voter_stats` endpoint added |
| Frontend updated | Sep 28 | Voter ID modal, reasoning modal, voting flow updated |
| Scraper fixed | Sep 28 | GSAP async polling, CDP click fallback, scroll library neutralization, no video |
| Scraper tested | Sep 28 | 24-site test: 21/24 complete, 2 timeouts (fixed with 90s timeout), 1 partial (fixed with stitched capture) |
| Full-page screenshot fixed | Sep 28 | Stitched viewport captures for scroll-hijacked sites — 14 captures → 11,738px full page |
| Pipeline updated | Sep 28 | Removed video/llava/enrich steps; added vlm step; new STEPS list |
| Config updated | Sep 28 | Removed deprecated file references; added v2 filenames |
| Enrich rewritten | Sep 28 | VLM feature extraction only; no taste_rationale.json generation |
| motion_capture.py deleted | Sep 28 | Deprecated legacy script removed |

### In Progress

| Task | Status | Notes |
|---|---|---|
| Voter pilot (recruit 3 designers) | Not started | Design is ready, need to recruit |
| Scraper fixes (GSAP, click-through, full-page) | Done | GSAP async polling, CDP fallback, scroll neutralization, no video |
| Metrics fixes (DOM-based asymmetry) | Not started | |
| MDPD model | Not started | |

### Not Started

| Task | Dependencies |
|---|---|
| Dimension discovery (factor analysis) | Voter pilot data |
| Dimension extractor (reasoning → dimensions) | Voter pilot data |
| MDPD nano-transformer | Dimension discovery |
| Residual vision model | MDPD model trained |
| 900-site scrape | Scraper fixes |
| Full 10k vote collection | Voter pilot validated |

---

## 13. Deletion Log

### Data to delete from `data_v1_archive/`

| Data | Action | Why |
|---|---|---|
| `taste_rationale.json` (100 files) | Delete | VLM-confabulated rationales — replaced by voter reasoning |
| `motion_storyboard.json` (100 files) | Delete | Only needed for keyframe extraction — no longer used |
| `frames/` directories (100 folders) | Delete | Video-derived keyframes — no longer used |
| `page@*.webm` (100 files) | Delete | Video recordings — no longer used |
| `embedding.json` (100 files) | Regenerate | Current embeddings are from VLM rationales — regenerate from voter reasoning |

### Code to deprecate

| File | Action | Why |
|---|---|---|
| `scripts/preprocess_video.py` | Deprecate | Video keyframe extraction — no longer needed |
| `scripts/motion_capture.py` | Delete | Already deprecated (legacy) |
| `scripts/vision_llm.py` | Deprecate | VLM rationale generation — VLM is now feature-only |
| `scripts/enrich.py` | Rewrite | Remove taste_rationale.json; keep stage2_vlm_raw.json as feature |
| `scripts/extract_taste.py` | Deprecate | "Rules of Taste" report — VLM-confabulated |
| `scripts/run_taste_gemini.py` | Deprecate | Gemini taste extraction — VLM-confabulated |
| `scripts/compile_dpo_dataset.py` | Replace | Replaced by `dpo_from_votes.py` (voter reasoning, not VLM rationales) |
| `scripts/compile_semantic_deltas.py` | Deprecate | Positional parity for DPO — no longer needed with MDPD |

### Pipeline steps to remove

| Step | Action | Why |
|---|---|---|
| `preprocess_video` | Remove from pipeline | No video, no keyframes |
| `llava` | Remove from pipeline | Already deprecated |
| `enrich` | Rewrite | VLM features only, no rationale generation |
| `compile` | Rewrite | No taste_rationale.json to merge |

---

## 14. What Needs to Change in Existing Code

### `scraper.py`
- Remove video recording
- Remove keyframe extraction
- Fix GSAP async loading
- Fix click-through robustness
- Fix full-page screenshot (neutralize scroll libraries)
- Add `scrollTo(0,0)` before hero screenshot

### `analyzer.py`
- Replace `asymmetry_score` with DOM-based layout imbalance
- Add 3×3 quadrant distribution
- Add more DOM features (font size variance, letter-spacing range, z-index depth)

### `enrich.py`
- Remove `taste_rationale.json` generation
- Keep `stage2_vlm_raw.json` as feature extraction
- Add validation gate (check claimed features against data)

### `index.html` (frontend)
- ✅ Voter ID modal — done
- ✅ Reasoning modal — done
- ✅ Voting flow updated — done
- ⬜ Add voter stats display (agreement rate, total votes)
- ⬜ Add "pause and resume" functionality

### `api/index.py`
- ✅ Accept `voter_id` + `reasoning` — done
- ✅ `/api/voter_stats` endpoint — done
- ⬜ Add voter authentication (prevent duplicate voter IDs)
- ⬜ Add rate limiting (prevent spam voting)

---

*End of document*
