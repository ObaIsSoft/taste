# AI Design Taste Engine: Idea Brief & Technical Specification

**Document Version:** 1.2 (sections 8.6 and 9–11 describe v2)  
**Date:** August 2026, updated October 2026  
**Classification:** Internal Concept Document  
**Author:** Concept Synthesis  

> **Status, October 2026.** Sections 1–8 and 12–16 are the original concept; section 8.6 adds the
> method alternatives considered for v2. Sections 9–11 describe v2 as built and running: the
> architecture, the method, the data, how each bias is handled, and the known limits. The first
> approach (fine-tuning a vision-language model to be the judge) failed for reasons recorded in
> `taste_engine_journal.md`, which also records, by date, what happened and why.
> `taste-engine/docs/operations.md` holds the runbooks and the database history.

---

## 1. EXECUTIVE SUMMARY

Current AI design tools generate *functional* websites. None generate *memorable* ones. This brief proposes the development of an AI system trained specifically on premium motion design, award-winning web experiences (Awwwards, Landbook, Savee), and design systems to serve as a **creative director copilot** — not a replacement for designers, but a taste engine that understands why premium design works and can translate that understanding into actionable design rationale, motion choreography, and structured design tokens.

---

## 2. PROBLEM STATEMENT

### 2.1 The Core Problem
Generative AI tools for web design (Figma Make, v0.dev, Builder.io) have solved *production velocity* but have failed to solve *creative direction*. They produce layouts that are structurally sound, accessible, and responsive — but aesthetically generic, emotionally flat, and devoid of brand personality. 

The gap is **taste**: the ability to understand why an Awwwards Site of the Day feels premium, how a GSAP scroll trigger creates emotional pacing, or why a specific typographic scale signals "luxury fintech" versus "SaaS startup."

### 2.2 Pain Points
- **Designers spend 60-70% of project time on research and reference gathering**, not creation.
- **Motion design is bottlenecked by technical expertise**: A designer may envision a scroll-driven 3D transform but lacks the GSAP/Three.js knowledge to execute it.
- **Design systems lack soul**: AI-generated systems are consistent but templated. They don't evolve with brand narrative.
- **No tool connects "reference" to "rationale"**: Designers can screenshot inspiration but cannot easily extract the underlying system (spacing tokens, easing curves, grid logic) from it.

### 2.3 Target User
- Senior UI/UX designers at agencies
- Creative directors seeking rapid concept validation
- Freelance web designers competing for premium clients
- Design educators teaching systems thinking

---

## 3. THE WHY

### 3.1 Why This, Why Now
1. **Vision-language models have crossed a threshold**: GPT-4V, Qwen2-VL, and Claude 3.5 Sonnet can now reason about visual hierarchy, color harmony, and spatial relationships with near-human accuracy.
2. **The data exists but is uncurated**: Awwwards has 15+ years of documented case studies. Landbook, Savee, and Behance contain millions of tagged design references. No one has structured this into a training corpus.
3. **Designers are already using AI but are unsatisfied**: 91% of designers using AI tools say output improves only when paired with creative direction. The market is begging for AI with taste.
4. **The infrastructure is democratized**: Fine-tuning multimodal models via LoRA/QLoRA is now possible on consumer-accessible cloud GPUs ($50–$200 on Colab/RunPod).

### 3.2 Why Existing Players Won't Solve This
- **Figma** optimizes for collaboration and component systems, not creative exploration.
- **Builder.io** optimizes for design-to-code translation, not taste generation.
- **Framer** optimizes for interaction fidelity, not AI-driven creative direction.
- **v0/Lovable/Bolt** optimize for shipping functional code, not award-winning craft.

None have an incentive to deeply curate Awwwards-level motion design data — it's too niche, too subjective, and too hard to evaluate automatically.

---

## 4. THE NEED

### 4.1 Market Need
The global AI web development market reached **$14.2 billion in 2026**, growing at 23.5% CAGR. However, the segment for **AI creative direction and taste engines** is effectively zero — not because there's no demand, but because no product exists to define the category.

### 4.2 User Need
Designers need:
- **Reference deconstruction**: "Show me the grid system, typographic scale, and motion logic behind this Awwwards winner."
- **Taste translation**: "I want this site to feel like [Reference A] but function like [Reference B]."
- **Motion choreography**: "Generate the GSAP timeline for a scroll-driven hero section that feels editorial and premium."
- **Design system generation**: "Create a Figma auto-layout structure and token set inspired by this reference."

### 4.3 Technical Need
Current VLMs understand *what* is in an image. They do not understand:
- Temporal motion (how a site behaves over time)
- Design token relationships (why `spacing-4` pairs with `font-size-lg`)
- Emotional resonance (why rounded corners + pastel palettes = "friendly fintech")
- Interaction choreography (scroll triggers, hover states, page transitions)

---

## 5. WHAT (Product Definition)

### 5.1 Product Name (Working)
**TASTE** — Training AI for Structured Taste Engine

### 5.2 Product Description
A multimodal AI system and companion toolset that:
1. **Ingests** design references (screenshots, Figma files, video walkthroughs, case studies)
2. **Analyzes** them through the lens of design systems, motion theory, and brand psychology
3. **Generates** structured outputs: design rationale, token systems, motion specs, and component structures
4. **Learns** from designer feedback to improve taste over time

### 5.3 Key Features (MVP → V1 → V2)

| Phase | Feature | Output |
|-------|---------|--------|
| **MVP** | Reference Analyzer | Upload screenshot → receive structured design critique (grid, type, color, motion impression) |
| **V1** | Motion Spec Generator | Upload reference → receive GSAP/Framer Motion timeline + easing curves |
| **V1** | Token Extractor | Upload reference → receive Figma-ready design tokens (color, spacing, typography) |
| **V2** | Creative Director Agent | Text brief + reference images → complete design system rationale + component structure |
| **V2** | Video Understanding | Upload site walkthrough video → temporal motion analysis + interaction map |

### 5.4 Product Form Factors
- **Figma Plugin**: Direct integration into designer workflow
- **Chrome Extension**: Analyze any live website with one click
- **Web Dashboard**: Dataset exploration, batch analysis, team collaboration
- **API**: For agencies building custom tools on top of TASTE

---

## 6. MARKET STUDY

### 6.1 Market Size
- **AI Web Development Market**: $14.2B (2026), projected $45B by 2030
- **Design Tools Market**: $12.4B (2026), growing at 18% CAGR
- **Addressable Niche (AI Creative Direction)**: Estimated $200M–$500M by 2028 (undefined category)

### 6.2 Market Trends
1. **Agentic AI**: Moving from text-prompt generators to autonomous planning agents (e.g., Elementor's Angie)
2. **Multimodal AI**: Convergence of vision, language, and code generation in single models
3. **Design System Democratization**: Small teams now expect enterprise-grade consistency
4. **Motion as Standard**: Static websites are increasingly seen as outdated; motion is expected

### 6.3 Target Market Segments
| Segment | Size | Willingness to Pay | Access Strategy |
|---------|------|-------------------|-----------------|
| Freelance Designers | ~500K globally | $20–$50/month | Figma Plugin marketplace |
| Design Agencies (10–50 people) | ~25K globally | $200–$500/month | Team dashboard + API |
| Enterprise Design Systems | ~5K globally | $1,000–$5,000/month | Custom integration + SLAs |
| Design Education | ~2K institutions | $50–$100/seat/month | Institutional licenses |

---

## 7. PRODUCT STUDY: COMPETITIVE LANDSCAPE

### 7.1 Direct Competitors (None)
No existing product trains a specialized model on premium web design references with the goal of taste extraction and creative direction.

### 7.2 Adjacent Competitors

| Product | Strength | Weakness vs. TASTE | Threat Level |
|---------|----------|-------------------|--------------|
| **Figma Make** | Native integration, GPT-5.6, publishes live sites | Generic output; no motion/taste understanding | High |
| **Builder.io Fusion** | Figma-to-code, inspiration capture via Chrome extension | Translation layer only; no creative reasoning | Medium |
| **Framer AI** | Best-in-class animations, designer-friendly | AI is assistive, not generative; no reference learning | Medium |
| **v0.dev** | Rapid React component generation from text | Code-first, not design-first; no taste layer | Low |
| **Lovable / Bolt.new** | Full-stack app generation | Functional, not beautiful; no design theory | Low |
| **Relume** | Proven conversion patterns, AI sitemaps | Formulaic; explicitly anti-creative-risk | Low |
| **Midjourney/DALL-E** | Stunning static image generation | No code, no interaction, no systems thinking | Low |

### 7.3 Competitive Moat
- **Curated Dataset**: 1,000+ structured Awwwards/Landbook entries with expert annotations
- **Designer RLHF**: Proprietary feedback from senior designers rating taste
- **Motion Understanding**: Unique capability to analyze and generate temporal design (GSAP/Three.js)
- **Design System Output**: Not just images — structured, editable Figma/code outputs

---

## 8. ALTERNATIVES CONSIDERED

### 8.1 Alternative 1: Build a General-Purpose Design AI
Train a foundation model from scratch on all design data (logos, packaging, UI, architecture).
- **Rejected**: Too broad, too expensive, competes with Adobe/Figma directly. Taste requires depth, not breadth.

### 8.2 Alternative 2: Pure Code Generation (v0.dev Clone)
Text prompt → React/Tailwind site.
- **Rejected**: Commoditized space. No differentiation. 50+ tools already exist.

### 8.3 Alternative 3: Static Image Generator for Web Design
Midjourney for UI mockups.
- **Rejected**: Designers need editable systems, not pretty pictures. Static images don't ship.

### 8.4 Alternative 4: Design Education Platform
Teach design theory via AI tutor.
- **Rejected**: Lower monetization. Education market is price-sensitive and slow.

### 8.5 Selected Approach: Taste Engine + Workflow Integration
Focus on **reference deconstruction** and **system generation** as a copilot within existing tools (Figma, Chrome). This is defensible, monetizable, and technically feasible.

### 8.6 Method Alternatives (v2)
How to learn taste, rather than which product to build. Each was considered; the right column says
why it was not chosen, or when it could return.

| Alternative | Why not, or not yet |
|---|---|
| **Language models judging from text** (v1: page summaries in, verdicts out) | Text cannot carry visual craft. v1's verdicts were invented, and 29% were not valid JSON |
| **Fine-tuning a vision-language model as the judge** (v1: SFT, then MADPO) | Failed on inputs, labels and testing, with far too few labels. It may return later to write critiques, not to judge |
| **A language model as the only judge** | It cannot stand in for the panel's taste, and it leans toward one side. Kept as the baseline to beat: blind, in both orders |
| **Rating each site from 1 to 10** | Scales drift between people and over time, and ratings bunch in the middle. Choosing between two is easier and more consistent |
| **One rater** (v1: 620 votes from one person) | Taste cannot be told from noise without agreement, and agreement needs several raters |
| **Crowd raters instead of designers** | They measure first-impression appeal, where simple, typical sites win, not craft. Possible later as a contrast |
| **Elo or TrueSkill** (v1's ratings) | Results depend on the order of votes. Bradley–Terry fits all votes at once and takes per-voter and side terms |
| **Every site against every other** | 84 sites make 3,486 pairs per round. Done only for the 14 calibration sites; the rest get pairs that balance coverage |
| **Active learning** (serving the most informative matchups) | More efficient, but the data then depends on the model of the moment. The pilot collects even coverage first; this can come later |
| **Stills and recordings judged together** | Mixes how a site looks with how it moves. Two rounds give two clean labels |
| **A fixed vocabulary for reasons** | Decides in advance what designers can say. Themes are found in their own words afterwards |
| **Judging the live sites** | They change, and load differently on each visit and network, so votes could not be reproduced. Votes are on fixed, pinned captures |
| **Training the image model end to end** | Too few labels (about 1,200 pilot votes). A frozen image model with small heads on top is the right size |
| **Collecting real bad sites for contrast** | Hard to source and to agree on. Degraded twins (one dimension damaged on purpose) and generated "AI default" pages instead |

---

## 9. HOW (Technical Architecture and Method)

### 9.1 System Overview (v2)
```
 manifest (1,006 award URLs, each id fixed to one URL + generated "AI default" pages)
     │
 CAPTURE  Playwright, Chromium full headless (GPU), 1440×900, the same for every site
     │    stills: hero + 3 screens · UX reel: intro, slow scroll, hovers, menu (H.264)
     │    DOM boxes, design tokens, animations + GSAP calls, load/jank/scroll metrics
     │    quality flags: blocked, down, parked, spam, gate left, page changed …
     │    degraded twins: typography / colour / spacing / layout damaged on purpose
     │
 ANALYSE  pixel + layout features · Claude descriptions (facts from fixed lists, no verdicts)
     │
 VOTE     Supabase (rules in Postgres) + a thin Flask API on Vercel + a neutral voting page
     │    visual round on stills · motion round on reels · A / B / equally good / can't decide
     │    what decided it: listed dimensions and the designer's own words, plus a written reason
     │    every vote pinned to the exact media version it showed; time on screen measured
     │    agreement and biases measured continuously (panel, repeats, designer pairs, rounds)
     │
 LEARN    Claude as a blind baseline judge (both orders) · pairwise scorer on frozen image
     │    embeddings: P(A beats B) = σ(score A − score B), one head per dimension
     │    synthetic labels: original beats its twin · award beats generated
     │
 USE      designers: a library ranked by craft, per dimension, with each site's tokens
          coding agents (MCP): capture the agent's page the same way → scores, nearest
          award sites and a critique written by Claude from scores and human reasons
```

### 9.2 Research Question
Can a model learn what experienced designers mean by well-made web design, per dimension, from
their pairwise judgments, well enough to rank and critique pages it has never seen? Three questions
are answered in order, and each can stop the project or change it:

1. **Do designers agree?** Agreement among designers on the same pairs is the ceiling for any
   model. If it is low, taste here is personal, and the product becomes per-designer.
2. **Does a language model already know?** Claude judging the same pairs, blind and in both orders,
   is the baseline a trained model must beat.
3. **Is it learnable from pixels and measurements?** A small scorer on frozen image embeddings,
   tested on sites it never saw.

### 9.3 Principles
- **Measure what the browser knows, and judge from what voters saw.** A model is never asked to
  report what the DOM or the pixels already show.
- **Language explains; it does not judge.** Descriptions are facts; verdicts come from votes and
  the trained scorer.
- **Capture what designers say without predefining it.** Listed dimensions are shortcuts.
  Designers can always use their own words, and themes are found in the text later.
- **Every vote points at exactly what it showed.** Media is published in versions named by a
  fingerprint of the files and never overwritten; a site id always means the same URL.
- **Measure bias rather than assume it away,** and correct it in the model (section 9.6).
- **Honest evaluation.** Split by site, never by pair. The ceiling is how often designers agree
  with each other. The Claude baseline is blind. Anything that tells a voter about their own or
  others' votes during voting is a change to the experiment, and is recorded as one.

### 9.4 Method: Collecting Judgments
- **Corpus.** 1,006 award-winning sites. The pilot uses 100 drawn at random with fixed seeds; 90
  passed QA, and 84 remained after a visual check removed pop-ups the scraper missed and an
  unfinished page.
- **Capture.** The same for every site, so captures are comparable:
  - four stills (the hero and three screens, by native, inner or wheel scrolling);
  - a scripted reel of 15–45 seconds: the intro, a slow scroll down and back, hovers, the menu;
  - the DOM boxes, the design tokens, the animations and GSAP calls;
  - load, jank and scroll metrics;
  - quality flags.

  Cookie walls, age gates and pop-ups are answered only inside the layer that blocks the page;
  anything unresolved fails QA.
- **Two rounds.** Visual (stills) and motion (reels) are judged separately, so "looks good, moves
  badly" is two clean verdicts rather than one muddled one.
- **Pairwise votes.** A is better, B is better, equally good, or can't decide; or report a broken
  capture. Choosing between two is easier and more consistent than scoring one.
- **What decided it.**
  - **Listed dimensions:** up to three, from six per round, each with a definition the voter
    can read.
  - **Own words:** any wording. Suggestions come only from the voter's own past words.
  - **A written reason:** required on a decisive vote when asked. It is asked on 1 pair in 3 at
    random, always on pairs other designers split on, and in the other round whenever it was
    asked there.
- **Which pair comes next.** The first of these that applies:
  1. an unanswered pair served in the last hour;
  2. the next calibration pair: all pairs among 14 visual and 8 motion sites, chosen as the most
     varied by measured features, judged by every designer in their own shuffled order;
  3. 10 calibration pairs again, sides swapped, to measure each designer's consistency;
  4. 10% of the time, a pair another designer judged, to keep measuring agreement;
  5. otherwise, the least-compared site against a random site this voter hasn't paired it with.

  Each site goes on the side it has been on less. Targets: 200 visual and 100 motion votes per
  designer.
- **The voting page.** Each choice has its reason:
  - **Neutral grey, light only.** A coloured frame changes how the sites' own colours read.
  - **A and B, not left and right.** Left and right make no sense on a phone.
  - **The sites fill the screen.**
  - **Pick, then explain.** The question becomes "What made A better?".
  - **All four outcomes look the same.** Loud A and B buttons push people away from ties.
  - **Invite links carry the code after the #,** so it never reaches a server log.
  - **The voter's name is always visible,** so a shared device can't mix up voters.
- **The panel.** Four designers and two spares. The voter guide asks them to judge craft: not the
  brand, the fashion of a style, or the language of the page.

### 9.5 Method: Learning, Evaluation and Use
1. **Baseline first.** Claude judges the calibration pairs in a fresh request per pair, in both
   orders, from a fixed prompt, with results sealed before the designers' results are read. That is
   the bar a trained model must beat, and it tells us whether training is worth it.
2. **A pairwise scorer.** A frozen, pretrained image model (SigLIP, CLIP or DINOv2) turns each screen
   into numbers. A small network on top learns a score per site from the votes, using the
   Bradley–Terry model: P(A beats B) = σ(score A − score B). It is the recipe behind PickScore,
   ImageReward and the LAION aesthetic predictor; with about 1,200 pilot votes, training only the
   part on top is the right size.
3. **One head per dimension (MDPD).** Each head trains on the votes that cited its dimension, plus
   the twins. The motion head uses reel frames, UX metrics and animation features.
4. **Labels and weights.**
   - Each designer's votes are weighted by their reliability in calibration.
   - Ties count as half a win each.
   - "Can't decide" and "broken" votes are left out of preference labels. Their words still show
     which trade-offs were hard.
   - Voter identity is part of the model: per-voter scores, not one averaged truth.
5. **Honest testing.**
   - Train and test are split by site, never by pair, with fixed seeds.
   - Test sites are chosen before anyone looks at results.
   - The ceiling is designer agreement.
   - Results are also reported within each kind of site (section 9.7).
6. **Critiques.** Claude writes them from the scores, the measured facts and the human reasons from
   the most similar pairs. Fine-tuning a vision-language model (SFT, then DPO) only makes sense
   later, if those critiques fall short and enough written reasons exist.

**Use.**
- **Designers:** a library ranked by craft, overall and per dimension; filters from the
  descriptions; each site's tokens as a ready style guide; "more like this" from the embeddings.
- **Coding agents over MCP:** the agent's page is captured the same way, scored per dimension,
  compared with the nearest award sites and critiqued. The award-versus-generated direction flags
  drift toward generic pages.
- **Research:** the agreement numbers show whether taste is learnable before more is spent.

### 9.6 Biases: How Each Is Prevented, Measured and Corrected
Votes measure taste, but other things lean on them too: which side a site was on, the screen it was
seen on, how tired the voter was, how much they looked. Nothing here is shown to voters while they
vote; `taste votes agreement` prints every view named below.

| Bias | Prevented by | Measured by | Corrected in training by |
|---|---|---|---|
| **Position.** Favouring a side | Balanced sides per site; repeats swap sides | `voter_bias.left_share` (near 0.5 is no lean), split by layout; `voter_consistency` | A side term in the pairwise model, per voter if they differ |
| **Device and layout.** One site at a time on a phone, both at once on a desktop | — | `voter_bias` split by `layout`; `client.viewport_width` | Layout as a covariate; votes cast without seeing both sites down-weighted |
| **Not looking at both sites.** Phones show A first | — | `vote_attention.saw_both`, `voter_bias.saw_both_share` | Votes where B was never opened dropped or down-weighted |
| **Hero only.** Never scrolling past the first screen | — | `vote_attention.scrolled_both` (visual) | A weight by attention; models compared with and without these votes |
| **Motion judged without watching** | — | `vote_attention.played_both` (motion) | Motion votes count only when both reels were played |
| **Fatigue** | Guide: sessions of 20–30 votes; calibration order shuffled per voter | `voter_effort`: early vs late median active time within sittings (a new sitting starts after 30 minutes without a vote) | A weight that falls with position in a long sitting |
| **Idle time counted as effort.** A tab left open, a break mid-pair | Guide: breaks are fine, time away is not counted | `vote_attention.active_seconds`, `left_page`; `voter_effort.idle_votes`, `left_page_votes` | Active time, never wall-clock time, for effort and fatigue |
| **Low effort** | Votes under 1 second are refused | `voter_effort.fast_votes`, `voter_consistency` | Per-voter reliability weights from calibration |
| **Ties and "can't decide" as an easy way out** | All four outcomes look the same | `voter_bias.tie_share`, `cant_decide_share`, with their words | Ties as half-wins; "can't decide" left out of preference labels |
| **Priming by the listed dimensions** | Own words always offered; suggestions only from the voter's own past words | `voter_bias.own_words_share` | Themes found from own words and reasons, not imposed |
| **Being asked for a reason** | Asked at random and on split pairs, never explained | `served_pairs.reason_requested` against outcome and time | A covariate: do asked votes differ? |
| **Visual verdict colouring the motion verdict** | Rounds in separate sessions | `round_differences`, including `same_session` | Same-session and separate-session differences compared |
| **Brand recognition** | The guide asks voters to judge craft | `vote_attention.opened_live` | Famous and unknown sites' win rates compared; a brand covariate if it matters |
| **Language** | — | `language_bias` (win share by page language) | A language covariate if a lean appears |
| **Kind of site.** A showcase site has one job and few constraints | Guide wording (open decision, section 9.7) | Win share by kind of site, once each site's kind is recorded | Kind as a covariate; results reported within each kind |
| **Feedback to a voter** about their own votes | Never shown during voting | The database history records any exception, with its time | Votes before and after compared |
| **Voter taste** (signal, not noise) | Calibration pairs every voter judges | `voter_agreement`, `pair_agreement` | Voter identity in the model |

The order of processing:
1. During voting, `taste votes agreement` after each voting day.
2. After each voting day, `taste votes export`: the votes, their events, the media versions they
   point at, and the sites.
3. A cleaning and weighting step (to build) writes one weight per vote, with the reason for each,
   so every exclusion is explainable.
4. Training uses those weights and the covariates above.

### 9.7 Known Limits
- **Form against function.** Nothing yet records what each site is for. A showcase site may win
  for having fewer constraints than a shop or a company site. In the pilot pool, by one reading:
  26 showcase, 22 shop or brand, 18 company, 12 editorial or institution, 6 hospitality. Showcase
  sites carry a third of the text and half the length of the others. A simulation showed such a bias
  would fill the top of a single ranking, while rankings within each kind stay intact; pairing
  within kinds barely helps. Research agrees that what makes a site appealing differs by domain
  (Papachristos & Avouris, 2013). The fix is to record each site's kind and report within kinds.
  The guide's tie-breaker ("which one would you rather show a client?") leans toward showcase
  sites; whether to change it is an open decision.
- **An award-only corpus.** Every site is "good"; contrast comes from twins and generated pages.
  Datasets made mostly of beautiful images can hide or even reverse effects (Parraga et al., 2025).
- **Experts, not users.** Designers reward craft and novelty; ordinary users prefer simple, typical
  sites (Tuch et al., 2012). TASTE learns designers' judgment of craft, not user appeal.
- **Desktop only.** One viewport, 1440×900. Mobile design is not judged.
- **A small panel.** Four designers; individual taste is treated as signal and modelled per voter.
- **What the data still lacks:**
  - who the voters are (experience, discipline), and their recorded consent to use their
    judgments and words;
  - each site's kind and purpose;
  - the page text;
  - held-out test sites.
- **Rights.** Screenshots and recordings of other people's sites are kept private: the votes,
  URLs and measurements can be shared, the media cannot.

### 9.8 Key Technical Challenges (as met)
| Challenge | How v2 handles it |
|-----------|------------|
| Hostile sites: gates, cookie walls, bot walls, scroll hijacking | Scoped multilingual gate answers, a page-change guard, a normal browser identity, stills by native, inner or wheel scroll; anything unresolved fails QA |
| Motion that stills cannot show | A scripted reel per site, Chromium's own scroll gesture, motion and UX metrics on a GPU-rendered page |
| Subjective evaluation | Calibration pairs every designer judges, swapped repeats, overlap, per-voter weighting |
| Votes drifting from what they judged | Media versions named by fingerprint, never overwritten; every pair and vote pinned to the version it showed |
| Effort hidden by idle time | Time on screen and in use measured per pair, separately from wall-clock time |
| LLM judges biased by position | A blind baseline in both orders; the trained judge works on embeddings, not text |
| A judge that never saw slop | Degraded twins and generated pages as contrast |

## 10. PROCESS (Development Roadmap)

### Done (September–October 2026)
- [x] v1: 100 sites, 620 valid one-person votes, LLM critics (SFT, MADPO): failed honestly
  (see the journal)
- [x] v2 capture, analysis, voting schema, voting app, agreement measurement
- [x] Scraper tested on 30 random sites, fixed, re-run
- [x] Pilot capture: 100 random sites, 90 passed QA, 84 in the pool after a visual check
- [x] Calibration (14 visual sites, 91 pairs; 8 motion sites, 28 pairs), six voters, the voting
  site live (3 October)
- [x] Active time per vote; every vote pinned to the exact media it showed (4 October)

### Pilot (now)
- [ ] Four designers reach their targets: 200 visual and 100 motion votes each, about 1,200 votes
- [ ] Measure agreement, consistency and biases daily; export after each voting day
- [ ] Record each site's kind and purpose; decide the guide's tie-breaker
- [ ] Choose held-out test sites before looking at results
- [ ] Run the blind Claude baseline (needs API credit)

### Scale (if the pilot clears its agreement target)
- [ ] A link-health pass over all URLs (about 17% of the sample was dead, parked or spam)
- [ ] Capture the remaining ~900 URLs, the twins (stills only) and the generated pages
- [ ] Train the pairwise scorer; per-dimension heads; evaluate against designer agreement

### Products
- [ ] Designer library (ranked, per dimension, tokens as style guides)
- [ ] MCP critic for coding agents

## 11. REQUIREMENTS

### 11.1 Hardware Requirements (Development)
| Phase | Minimum | Recommended |
|-------|---------|-------------|
| Dataset curation | MacBook Pro M1, 16GB RAM, 512GB SSD | Same (sufficient) |
| Local inference testing | MacBook Pro M1, 16GB RAM | Mac Studio, 32GB+ RAM |
| Model fine-tuning | Google Colab (T4) / Kaggle | RunPod A100 (40GB VRAM) |
| Production inference | Cloud VPS (4 vCPU, 16GB) | Kubernetes cluster with GPU nodes |

### 11.2 Software Stack (v2)
| Layer | Technology |
|-------|------------|
| Capture | Python 3.12, Playwright (Chromium full headless), ffmpeg, Pillow, NumPy |
| Pipeline | The `taste` command line (`taste-engine/`), pydantic settings |
| Language | Claude API (Opus 5.5 by default) through the Message Batches API |
| Voting data | Supabase: Postgres with the voting rules and append-only media versions, private Storage with signed links |
| Voting site | Flask function and static pages on Vercel |
| Learning (next) | PyTorch, frozen image encoders (SigLIP / CLIP / DINOv2) |

### 11.3 Human Resources
| Role | Commitment | When Needed |
|------|------------|-------------|
| Full-stack developer (you) | Full-time | Day 1 |
| Senior designer (advisor) | 5–10 hrs/week | Phase 1 |
| ML engineer (contract) | Project-based | Phase 2 |
| Designer annotators | 10–20 people, gig work | Phase 1–2 |

### 11.4 Budget Estimate
The project runs on free tiers and stays there: Supabase free (1 GB storage, 5 GB egress a month)
and Vercel Hobby. Media is sized for it: about 1 MB a site (stills plus a 0.45 MB reel), so about
1,000 votable sites fit. Claude use is small: descriptions cost about $6 per 1,000 sites at batch
prices. The original phase budgets below assumed a funded product and are kept for reference.

| Phase | Cost Range | Primary Expenses |
|-------|------------|------------------|
| Phase 0 | $0–$500 | API calls (Claude/GPT), domain, hosting |
| Phase 1 | $1,000–$3,000 | API calls, cloud GPU credits, designer stipends |
| Phase 2 | $5,000–$15,000 | GPU rental, contractor fees, marketing |
| Phase 3 | $50,000–$200,000 | Full-time hires, infrastructure, sales |

### 11.5 Data
**What is collected, and what it is for.**

| Data | Source | Used for |
|---|---|---|
| Four stills and a reel per site, kept as versions named by a fingerprint of the files | capture | image and frame embeddings, then the visual and motion scores |
| UX metrics: load, layout shift, dropped frames, scroll hijack, reduced motion | capture | motion and UX inputs |
| Fonts, type scale, palette, spacing; the animation list | capture | inputs, and a style guide for designers |
| Pixel and layout features (every measured value, none hand-picked) | analysis | inputs, explaining scores, choosing varied calibration sites |
| Claude descriptions: language, anything covering the page, whether it is a live site (facts only) | describe | search and filters; never quality labels |
| Votes: outcome, sides, the media versions shown | designers | **the real labels** |
| Listed dimensions, own words, written reasons | designers | per-dimension heads, critiques, themes found in their words |
| How each vote was cast: device, layout, what was looked at, time on screen and in use | the voting page | bias correction and vote weights (section 9.6) |
| Original beats each degraded twin | automatic | one label per dimension |
| Award site beats generated page | automatic, generator not built | the direction away from generic pages; a weaker label |

**Where each vote's data lives.**

| Data | Recorded in | Written by |
|---|---|---|
| Which capture was on which side, the verdict, and the media version each side showed | `votes.left_capture`, `right_capture`, `outcome`, `left_media`, `right_media` | `cast_vote`, from the served pair |
| When the pair was served, and the wall-clock time to vote | `served_pairs.served_at`, `votes.seconds_to_vote` | `next_pair`, `cast_vote` |
| Time on screen, in front and in use (up to `idle_cutoff_seconds` after the last input or a playing reel); times the voter left the page; the longest stretch without input; reloads | `votes.client.timing` | the voting page, with each vote |
| Whether a reason was asked for | `served_pairs.reason_requested` | `next_pair` |
| Listed dimensions and the voter's own words | `votes.dimensions`, `votes.own_terms` | `cast_vote` |
| Session, position in the session, layout (`tabs`, `stacked`, `side_by_side`), screen size, pixel ratio, touch or mouse | `votes.client` (an open object; new keys need no schema change) | the voting page, with each vote |
| What the voter looked at: phone tab opened, screens scrolled, reels played, live site opened | `vote_events` | the voting page, as it happens |
| Every published media version, with each file's hash | `capture_media` (append-only) | `taste publish` |
| The page's language, and whether anything covered it | `captures.description` | `taste describe`, then `taste publish` |

The limits (the size of `client`, the low-effort threshold, the idle cut-off, the gap that starts a
new sitting) live in `voting_config`, and each round's vote target in `round_targets`.
`voting_facts()` gathers them for the voting page and the voter guide.

**Storage and exports.** Votes live in Supabase, with no automatic backups on the free tier; an
export after each voting day is the backup. Captures and media stay on the capture machine and in a
private bucket; the site list (`list.md`, `taste-engine/manifest/sites.csv`) and the v1 archive are
kept out of the repository.

**Legal.** Screenshots of public pages for research; the voting site never embeds live sites; media
is never published with the data.

---

## 12. FEASIBILITY STUDY

### 12.1 Technical Feasibility: HIGH
- Vision-language models (Qwen2-VL, GPT-4V) already demonstrate strong visual reasoning
- Fine-tuning via QLoRA is well-documented and cost-effective
- Figma Plugin API and Chrome Extension APIs are mature
- GSAP/Three.js are text-based and thus LLM-friendly

### 12.2 Data Feasibility: MEDIUM
- **Pros**: Awwwards, Landbook, Savee, Behance contain millions of references; Figma Community has structured files
- **Cons**: Bulk scraping may violate ToS; case study text is sparse; video walkthroughs are unstructured; obtaining high-quality annotations is labor-intensive
- **Mitigation**: Partner with design studios; focus on public case studies; use synthetic data augmentation

### 12.3 Market Feasibility: HIGH
- 72% of designers already use generative AI tools
- 91% say AI improves output only with creative direction — proving unmet demand
- No direct competitor in the "taste engine" niche
- Figma plugin marketplace provides built-in distribution

### 12.4 Financial Feasibility: MEDIUM
- **Low burn**: Can reach MVP with <$1,000 using existing APIs and local inference
- **Monetization path**: Clear (SaaS subscription, API usage, enterprise licenses)
- **Risk**: Customer acquisition cost may be high in a crowded design tools market

### 12.5 Competitive Feasibility: MEDIUM-HIGH
- Figma, Builder.io, and Framer could replicate this if they prioritize it
- **Moat**: Curated dataset + designer RLHF network + motion-specific expertise
- **Window**: 12–18 months before major players potentially enter this niche

### 12.6 Overall Feasibility Score: **7.5/10**
Technically achievable, market-validated, and financially lean to start. Primary risks are data acquisition and competitive replication.

---

## 13. PROJECTED OUTCOMES

### 13.1 Success Scenario (Probability: 35%)
**Timeline:** 18–24 months

**Indicators:**
- 1,000+ paying users at $30–$50/month average revenue
- Recognized as the "go-to" tool for design reference analysis
- Figma plugin in top 50 most popular
- API used by 10+ design agencies
- Raised seed round ($500K–$2M) or reached profitability

**Outcome:**
TASTE becomes the default creative director copilot for web designers. The dataset and RLHF feedback loop create a defensible moat. The product expands into video game UI, app design, and brand identity systems. Acquired by Figma, Adobe, or Builder.io for $10M–$50M, or reaches $5M ARR as an independent tool.

### 13.2 Moderate Success Scenario (Probability: 40%)
**Timeline:** 12–18 months

**Indicators:**
- 200–500 paying users
- Strong niche following among motion designers and creative agencies
- Figma plugin generates $5K–$15K MRR
- Dataset becomes valuable open-source/community resource

**Outcome:**
TASTE survives as a profitable indie SaaS ($100K–$300K ARR). The founder maintains full ownership. The product serves a loyal but smaller market. Potential pivot into design education or agency services.

### 13.3 Failure Scenario (Probability: 25%)
**Timeline:** 6–12 months

**Indicators:**
- <50 paying users after 6 months of paid availability
- Designers find outputs generic or unreliable
- Figma or Builder.io releases a native feature that covers 80% of use cases
- Data acquisition proves legally or technically intractable

**Outcome:**
Project shuts down or pivots. Valuable assets: curated dataset (can be sold/licensed), Figma plugin codebase, designer network. Founder gains deep expertise in multimodal AI + design systems, which is highly employable. Total financial loss: $3,000–$10,000.

### 13.4 Expected Value Calculation
```
(0.35 × $15M exit value) + (0.40 × $200K ARR business) + (0.25 × -$5K loss)
= $5.25M + $80K - $1.25K
= ~$5.33M expected value
```
*Note: This is highly speculative but illustrates the asymmetric upside of the venture.*

---

## 14. DERIVATIVES & FUTURE APPLICATIONS

### 14.1 Immediate Derivatives (0–12 months)
1. **Design Education Module**: AI tutor that teaches design theory using real-world references
2. **Accessibility Auditor**: Analyze premium sites for WCAG compliance and suggest accessible alternatives
3. **Brand Consistency Checker**: Upload brand guidelines + new design; AI scores alignment
4. **Competitive Analysis Tool**: Compare your site against 5 Awwwards winners in your industry

### 14.2 Medium-Term Derivatives (1–3 years)
5. **Motion Design Marketplace**: Designers sell curated GSAP/Framer motion presets validated by the AI
6. **Design System Generator**: From brand brief → complete Figma design system + tokens + documentation
7. **A/B Test Designer**: Generate design variants based on proven conversion patterns vs. award-winning aesthetics
8. **No-Code Animation Tool**: Visual interface for GSAP powered by AI-suggested choreography

### 14.3 Long-Term Derivatives (3–5 years)
9. **Autonomous Design Agent**: Given a product brief, researches competitors, generates concepts, and produces production-ready design systems
10. **Cross-Domain Taste Engine**: Expand from web design to architecture, fashion, industrial design, automotive UI
11. **Real-Time Design Collaboration**: AI participates in design critiques, suggesting improvements during live Figma sessions
12. **Generative 3D Web Experiences**: AI generates Three.js/WebGL experiences from mood boards and reference videos

### 14.4 Platform Pivot Opportunities
- **B2B Enterprise**: White-label taste engine for large brands' internal design systems
- **Marketplace**: Connect designers with motion developers based on AI-generated specs
- **Data Business**: Sell curated, annotated design dataset to researchers and larger AI companies
- **Education**: Certification program for "AI-Augmented Design" using TASTE as the platform

---

## 15. GO/NO-GO DECISION FRAMEWORK

### GO if:
- [ ] You can commit 10+ hours/week for 6 months
- [ ] You have access to 3+ senior designers willing to provide feedback
- [ ] You are comfortable with Python, APIs, and basic ML concepts
- [ ] You have $1,000–$3,000 available for Phase 1–2 expenses
- [ ] The validation post (Phase 0) receives 50+ positive responses from designers

### NO-GO if:
- [ ] You expect to train a foundation model from scratch on your MacBook
- [ ] You are unwilling to do manual data curation for 100+ hours
- [ ] You need revenue within 3 months
- [ ] You have no design background or designer network
- [ ] You view this as a "get rich quick" SaaS play

---

## 16. APPENDIX: GLOSSARY

| Term | Definition |
|------|------------|
| **Awwwards** | Platform recognizing excellence in web design |
| **GSAP** | GreenSock Animation Platform — industry-standard JavaScript animation library |
| **QLoRA** | Quantized Low-Rank Adaptation — efficient fine-tuning method for large models |
| **RLHF** | Reinforcement Learning from Human Feedback |
| **VLM** | Vision-Language Model — AI that processes both images and text |
| **Design Tokens** | Named variables for colors, spacing, typography in design systems |
| **Figma Auto-Layout** | Constraint-based responsive layout system in Figma |
| **WebGL** | JavaScript API for rendering 3D graphics in browsers |
| **LoRA** | Low-Rank Adaptation — parameter-efficient fine-tuning technique |
| **SOTD** | Site of the Day (Awwwards award category) |

---

*End of Document*
