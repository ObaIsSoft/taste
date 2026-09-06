# AI Design Taste Engine: Idea Brief & Technical Specification

**Document Version:** 1.0  
**Date:** August 2026  
**Classification:** Internal Concept Document  
**Author:** Concept Synthesis  

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

---

## 9. HOW (Technical Architecture)

### 9.1 System Overview
```
┌─────────────────────────────────────────────────────────────┐
│                        INPUT LAYER                          │
│  Screenshot │ Figma JSON │ Video Walkthrough │ Text Brief   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    PROCESSING LAYER                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Vision Enc.  │  │ Text Enc.    │  │ Motion Analyzer  │  │
│  │ (CLIP/SigLIP)│  │ (LLM Backbone)│  │ (Frame Extract)  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                     REASONING LAYER                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Multimodal LLM (Qwen2-VL / GPT-4V / Custom VLM)     │  │
│  │  Fine-tuned on curated design corpus                 │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                      OUTPUT LAYER                           │
│  Design Rationale │ Token System │ GSAP Timeline │ Figma   │
│  JSON Structure   │ Color Palette│ Easing Curves │ Plugin  │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 Data Pipeline
1. **Ingestion**: Playwright-based scraper captures screenshots, metadata, tech stack
2. **Annotation**: Local vision model (LLaVA 7B via Ollama) generates initial structural analysis
3. **Enrichment**: Claude/GPT-4V API writes expert-level design rationale
4. **Structuring**: Custom parser converts analysis into standardized JSON schema
5. **Storage**: SQLite (metadata) + filesystem (images) + JSONL (training format)
6. **Quality Filter**: Human designer rates entries; only 7+/10 enter training corpus

### 9.3 Model Architecture
- **Base Model**: Qwen2-VL-72B or LLaVA-OneVision (open, multimodal, strong vision reasoning)
- **Fine-tuning Method**: QLoRA (4-bit quantization + Low-Rank Adaptation)
- **Training Data Format**: Interleaved image-text sequences with design-specific tokens
- **Reward Model**: Separate lightweight model trained on designer preference rankings (RLHF)
- **Inference**: Local (Ollama with custom GGUF) for MVP; API for V1+; cloud GPU for batch

### 9.4 Key Technical Challenges
| Challenge | Mitigation |
|-----------|------------|
| Video understanding | Extract keyframes at interaction points; use video-captioning model as preprocessor |
| Subjective evaluation | Designer-in-the-loop RLHF; multi-dimensional scoring (aesthetics, usability, accessibility) |
| Figma JSON generation | Train on public Figma community files; validate against Figma Plugin API schema |
| Copyright/data rights | Partner with studios for licensed data; focus on publicly documented case studies |
| Motion code correctness | Render generated GSAP in headless Chrome; validate with visual diff |

---

## 10. PROCESS (Development Roadmap)

### Phase 0: Validation (Weeks 1–4)
- [ ] Scrape 50 Awwwards SOTD entries with metadata
- [ ] Build automated annotation pipeline (screenshot → LLaVA → Claude → JSON)
- [ ] Post in design communities (r/web_design, Designer News) to validate demand
- [ ] Build Figma plugin skeleton or Chrome extension MVP
- **Deliverable**: Dataset of 50 curated entries + community validation signals

### Phase 1: Dataset & Taste Layer (Months 2–4)
- [ ] Scale dataset to 1,000 curated entries
- [ ] Recruit 5–10 senior designers for annotation and RLHF
- [ ] Build reference analyzer: upload screenshot → structured critique
- [ ] Launch Twitter/X bot posting daily "Why This Design Works" threads
- **Deliverable**: Working reference analyzer + 1,000-entry dataset + designer network

### Phase 2: Copilot Features (Months 5–8)
- [ ] Add motion spec generation (GSAP timeline from reference)
- [ ] Add token extraction (color, spacing, typography from screenshot)
- [ ] Fine-tune 7B vision model on curated dataset via QLoRA on cloud GPU
- [ ] Launch paid Figma plugin ($20–$50/month)
- **Deliverable**: Figma plugin with 3 core features + 100 paying users

### Phase 3: Platform (Months 9–18)
- [ ] Add video understanding (site walkthrough analysis)
- [ ] Build team collaboration dashboard
- [ ] Train custom reward model on 10,000+ designer ratings
- [ ] Launch API for agency integration
- [ ] Explore enterprise design system partnerships
- **Deliverable**: Full platform + API + 1,000+ paying users

---

## 11. REQUIREMENTS

### 11.1 Hardware Requirements (Development)
| Phase | Minimum | Recommended |
|-------|---------|-------------|
| Dataset curation | MacBook Pro M1, 16GB RAM, 512GB SSD | Same (sufficient) |
| Local inference testing | MacBook Pro M1, 16GB RAM | Mac Studio, 32GB+ RAM |
| Model fine-tuning | Google Colab (T4) / Kaggle | RunPod A100 (40GB VRAM) |
| Production inference | Cloud VPS (4 vCPU, 16GB) | Kubernetes cluster with GPU nodes |

### 11.2 Software Stack
| Layer | Technology |
|-------|------------|
| Scraping | Python, Playwright, Pillow |
| Local ML | Ollama, LLaVA 7B/13B, CLIP |
| Cloud ML | PyTorch, Transformers, PEFT (QLoRA), Unsloth |
| Data Storage | SQLite, JSONL, Git LFS |
| Backend | Python (FastAPI) or Node.js |
| Frontend | React / Next.js |
| Figma Plugin | Figma Plugin API, TypeScript |
| Chrome Extension | Manifest V3, JavaScript |
| APIs | Claude API, OpenAI GPT-4V, Figma API |

### 11.3 Human Resources
| Role | Commitment | When Needed |
|------|------------|-------------|
| Full-stack developer (you) | Full-time | Day 1 |
| Senior designer (advisor) | 5–10 hrs/week | Phase 1 |
| ML engineer (contract) | Project-based | Phase 2 |
| Designer annotators | 10–20 people, gig work | Phase 1–2 |

### 11.4 Budget Estimate
| Phase | Cost Range | Primary Expenses |
|-------|------------|------------------|
| Phase 0 | $0–$500 | API calls (Claude/GPT), domain, hosting |
| Phase 1 | $1,000–$3,000 | API calls, cloud GPU credits, designer stipends |
| Phase 2 | $5,000–$15,000 | GPU rental, contractor fees, marketing |
| Phase 3 | $50,000–$200,000 | Full-time hires, infrastructure, sales |

### 11.5 Data Requirements
- **Initial corpus**: 1,000 curated website entries (screenshot + metadata + rationale)
- **Growth target**: 10,000 entries by Phase 3
- **Annotation standard**: Each entry must include: layout type, color tokens, typography classification, motion impression, design rationale, quality score
- **Legal**: All entries must have documented permission or fall under fair use for research/annotation

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
