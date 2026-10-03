# TASTE engine v2: build log, decisions and findings

As of 3 October 2026, updated after the scraper fixes and the re-run (section 4b). Work is on
the `v2-rebuild` branch and has not been pushed. The live Supabase
project still runs v1, and nothing here has touched it.

Images referenced below live in `data/reports/2026-10-03-batch/`. That folder is git-ignored, so the
images exist only on this machine.

## Contents

1. [Where things stand](#1-where-things-stand)
2. [Decisions we agreed](#2-decisions-we-agreed)
3. [What was built, and why](#3-what-was-built-and-why)
4. [Scraper test on 30 random sites (3 October)](#4-scraper-test-on-30-random-sites-3-october)
   - [4b. Re-run after the fixes](#4b-re-run-after-the-fixes)
5. [Problems found, by severity](#5-problems-found-by-severity)
6. [The external code review: verdicts](#6-the-external-code-review-verdicts)
7. [Training: data, method and use](#7-training-data-method-and-use)
8. [Order of work: 100 sites before 1,000](#8-order-of-work-100-sites-before-1000)
9. [Proposed next steps](#9-proposed-next-steps)
10. [How to reproduce](#10-how-to-reproduce)

---

## 1. Where things stand

| Area | State |
|---|---|
| Package, settings, manifest (1,006 award URLs), CLI, guardrails | Done |
| Capture: stills, UX reel, motion and UX metrics, quality flags, degraded twins, batch runner | Done. Bugs found on 30 random sites were fixed and the same sites re-run (section 4b) |
| Analysis: pixel and layout features; Claude factual descriptions (Batch API) | Done |
| Voting schema (rules in Postgres), publishing to Supabase | Done. **Not applied to live**; it drops the v1 tables |
| Voting app: API and UI, redesigned; designers' own words alongside the chips | Done. Preview only, with a stand-in database |
| Agreement measurement and reason policy | Done |
| Generated "slop" pages (`taste generate`) | Not started |
| Embeddings, dataset, trainer, Claude baseline judge, evaluation | Not started |
| Cleanup of v1 code and files, README | Not started; needs your approval |

All 80 automated tests pass. They cover:

- the capture code, using a local test page in a real browser;
- the voting rules, in a throwaway Postgres;
- the API;
- the voting page in a real browser at four screen sizes.

### Commits on `v2-rebuild`

| Commit | What |
|---|---|
| `9f56ebd` | Snapshot of your uncommitted v2 work before the rebuild, so nothing could be lost |
| `331aeba` | Package foundation: settings, manifest, CLI, guardrails |
| `7f5bba7` | Website capture: stills, UX reel, motion and UX metrics, quality flags |
| `438b3c3` | Four capture fixes found on real sites |
| `a149af4` | Feature analysis and factual Claude descriptions |
| `8948870` | Voting schema with its rules in Postgres; Supabase publishing |
| `c983b6b` | Voting app on the v2 schema: thin API, mobile-first UI |
| `9fae391` | One shared Batch API module |
| `202867e` | Voting UI redesign: neutral, A and B, decide then explain, invite links |
| `eef6bec` | Motion round stacks both recordings on phones |
| `2521f78` | Agreement views, reason policy, one "can this be shown" rule, calibration in both rounds |

---

## 2. Decisions we agreed

- **A fresh start.** v1 votes and captures are purged and not reused. v1 code stays until a final
  cleanup you approve, and v1 data folders are left alone.
- **The scrape.** All 1,006 award URLs from `list.md`, captured fresh with one scraper version and
  one viewport (1440×900).
- **A contrast set for "slop".** You can't source 200 bad sites, so the contrast set has two parts:
  - *Degraded twins:* each award site re-captured with its typography, colour, spacing or layout
    deliberately damaged.
  - *Claude-generated pages:* "AI default" landing pages built from short briefs.
- **Motion is captured, not guessed.** Each site gets a scripted UX reel, plus measured UX metrics.
  Voting is split into a visual round (stills) and a motion round (reels), so each label stays clean.
- **Voters.** Four designers. A pilot starts with 14 calibration sites (91 pairs per round) that every
  designer judges, then moves to adaptive pairs.
- **Outcomes.** A is better, B is better, Equally good, Can't decide, or Broken.
- **Models.** Claude Opus 5.5 by default, or Sonnet 5.5 for cost, through the Batch API at half price.
- **Storage.** Supabase, with a private bucket and short-lived signed links.
- **How we work.** I commit verified steps. When you ask a question I research and answer without
  changing the project.
- **No lookup tables for what designers say.** A designer can tap one of the listed dimensions, add
  their own words (a term of their own) and always write a sentence. Nothing they say has to fit a
  predefined list. Autocomplete only offers a designer their own past words.
- **No hand-picked metric lists.** Every metric the capture measures reaches the features and the
  database automatically; only a few summaries are computed by hand.

---

## 3. What was built, and why

### Foundation

- **One installable package with one command line (`taste`), and every setting in one place**
  (`settings.py`, overridable with `TASTE_` environment variables).
  *Why:* v1 had overlapping scripts, hardcoded paths and two scrapers that disagreed. One entry
  point and one settings file stop that happening again.
- **A manifest (`manifest/sites.csv`) with stable ids 1–1,006, read from `list.md`.** Broken URLs
  are repaired on import.
  *Why:* every capture, vote and training row needs a stable site id.
- **Guardrails:** ruff, vulture (dead code), CI, pre-commit hooks that block secrets, `.env` files and
  media in git.
  *Why:* you asked for no ghost code, floating code, parallel systems or hardcoding. These catch it
  automatically.

### Capture

Each site gets two visits in a fresh, isolated browser process.

1. **Analysis visit:**
   - Stills of the hero and the next three screens.
   - The layout of content boxes and the design tokens (fonts, sizes, colours, spacing).
   - A wheel test that measures dropped frames and detects scroll hijacking.
   - Running animations, plus a hook that catches GSAP calls.
   - Page-change counts and load timings.
2. **Reel visit:** a scripted 15–30 second recording. It waits through the intro, scrolls slowly
   through three screens, returns to the top, hovers over a few links, and opens the menu if there
   is one. It is transcoded to H.264 MP4.
3. **Reduced-motion check:** whether animations stop when the browser asks for less motion.

The visits feed:

- **Quality flags:** blank hero, bot block, not found, navigated away, overlay remaining, reel missing.
- **Degraded twins:** the same capture with CSS injected that damages one dimension.
- **A batch runner:** each capture runs in its own subprocess, with retries and a resumable state.

*Why:* a still shows the interface, not the experience. A site can look elite and still hijack the
scroll or make you wait six seconds. Recording the same choreography on every site makes reels
comparable, and the metrics catch "good UI, bad UX" even when a voter misses it. Separate processes
mean one crashing site can't take down a batch.

Fixes made after the first two real sites (`438b3c3`):

- A "protected by reCAPTCHA" footer was wrongly flagged as a bot block.
- Content-visible time included a network wait.
- The change counter never started.
- Poster frames could be blank.

### Analysis and descriptions

- **Pixel features:**
  - whitespace relative to the background colour;
  - colourfulness;
  - edge density;
  - palette.
- **Layout features:**
  - where the text sits;
  - how much of the screen is media;
  - type-size variety;
  - spacing regularity.
- **Claude descriptions:** facts only, each answer chosen from a fixed list, with no field for quality.

*Why:* v1's model was given VLM verdicts that turned out to be invented, and 29% weren't valid JSON.
Facts from fixed lists can't hallucinate a judgment. The features are inputs, and they help explain
scores.

### Voting schema and publishing

Every voting rule lives in Postgres, in `supabase/migrations/0001_v2_voting.sql`:

- who may vote (invite codes);
- which pair a voter sees next: unfinished pair, calibration, swapped repeats, overlap, adaptive;
- what a valid vote is: dimensions required for A or B, reasons when asked, no double votes;
- that a "broken" report takes the capture out of the pool.

Row-level security is on with no policies, so browsers can't touch the tables. Media sits in a
private bucket and is served through short-lived signed links.

*Why:* rules in one place can't drift between the UI, the API and the database. v1 had no way to tie
a vote to a voter, and its tables were open to anyone.

### Voting app

- **A thin API.** It checks the invite code, calls the database functions, signs media links, and
  turns database errors into clean HTTP errors.
- **The redesign (`202867e`).** Each change is followed by its reason.
  - *Neutral grey, light only, no accent colour.* A dark or blue frame changes how the sites' own
    colours look, and voters on different settings would see different things.
  - *The sites are called A and B.* "Left" and "right" make no sense on a phone. The database
    still stores left and right.
  - *The sites fill the screen.* On a phone the site went from about 170px tall to about 550px.
  - *Pick a verdict, then say what decided it.* The question becomes "What made A better?",
    which is clearer.
  - *All four outcome buttons look the same.* Loud A and B buttons nudge people away from
    "Equally good" and "Can't decide".
  - *Report sits on each site and asks first.* It removes a capture from the pool.
  - *Invite links* (`#invite=CODE`). Designers click rather than type, and the code never reaches
    a server log.
- **The motion round stacks A above B on phones (`eef6bec`).** A recording's size is set by the
  screen's width, so stacking costs nothing. It also means nobody votes without seeing B.

| Before | After |
|---|---|
| ![before](../data/reports/2026-10-03-batch/ui/before-laptop-dark.png) | ![after](../data/reports/2026-10-03-batch/ui/laptop-visual.png) |
| ![before phone](../data/reports/2026-10-03-batch/ui/before-phone.png) | ![after phone](../data/reports/2026-10-03-batch/ui/phone-visual.png) |

### Agreement and reasons (`2521f78`)

- **Views that line up votes regardless of which side each site was on.**
  - `pair_agreement`: how the panel split on each pair.
  - `voter_consistency`: each designer on the swapped repeats.
  - `voter_agreement`: each pair of designers.
  - `round_differences`: where a designer's visual and motion verdicts differ, with the dimensions
    and reasons from both rounds.
  - `taste votes agreement` prints them all.
- **Reasons where they explain a difference.**
  - A pair other designers split on always asks for a reason.
  - A pair already judged in the other round asks exactly when that round did, so the two reasons
    pair up.
  - Voters are never told why they're asked.
- **One `servable` rule.** It fixed a bug where calibration kept showing captures that had been
  reported broken.
- **`taste calibrate` creates both rounds by default.**

*Why:* nothing measured agreement before, and agreement is the ceiling for any model. A visual
"B" and a motion "A" on the same pair is the "good UI, bad UX" signal, not a conflict. We don't ask
"why did you change your mind": that would reveal the hidden repeats and other people's votes, and
teach voters that disagreeing costs extra typing.

---

## 4. Scraper test on 30 random sites (3 October)

**Setup.** 30 sites drawn at random (seed 20261003) from the v2 manifest, plus all four twins for 3 of
them: 42 captures. It ran the scraper exactly as committed, with no changes, using the default 2
workers.

**Timing.**

- 42 captures took 18.6 minutes. The 30 originals took 13.7 minutes, about 27 seconds per site with 2
  workers.
- A single site takes 40–76 seconds; a twin takes 50–79 seconds, because twins also record a reel.
- At that rate, 1,006 originals take about 8 hours.

### Results by site

I reviewed every capture by eye against the contact sheets.

| Verdict | Count | Sites |
|---|---|---|
| Good | 15 | widehue (31), robbyyeager (55), cta-gules (112), heronaiapp (130), wild-ag (133), elinakustlyvy (298), mcmaster (399), lsv-invictus (490), middlename (512), bpando (637), mexican art museum (652), mockup.maison (777), glyphsapp (814), cltv.film (864), archier (939) |
| Usable but weak | 3 | lekhoa (900, "under construction"), barletta (996, "coming soon", 1 still), dorot (349, a "Skip" click changed the timeline shown) |
| **Wrong, but passed QA** | **6** | bellussi (8, Italian age gate on every still), flyward (388, "Explore" clicked, ended on `/private-service`), limlondon (531, parked domain), ot.studio (540, stuck on a flashing-lights warning), aster.studio (850, parked domain), madeleinedalla (946, taken over by casino spam) |
| QA failed, correctly | 2 | maisonmargiela (638, Cloudflare 403; the site is down for everyone with a 522), revolut (683, Cloudflare blocked our browser; works for you) |
| Capture failed | 4 | oxigen (21), aralesk (149), illoca (308): a 2.5-second screenshot timeout bug. mfisher (627): the domain no longer exists |

So **15 of 30 (50%) are clearly good**. Automatic QA passed 24, but 6 of those were wrong: a 25%
false-pass rate. **Link rot accounts for 5 of the 30 (17%)**:

- parked domains: limlondon, aster;
- spam takeover: madeleinedalla;
- dead: mfisher;
- down: maisonmargiela.

Across the full manifest that's roughly 170 bad URLs, before the scraper even runs.

### Contact sheets

Each row is one site's four stills, with its QA result and overlay actions on the left.

- ![sheet 1](../data/reports/2026-10-03-batch/sheet-1.jpg)
- ![sheet 2](../data/reports/2026-10-03-batch/sheet-2.jpg)
- ![sheet 3](../data/reports/2026-10-03-batch/sheet-3.jpg)

### Degraded twins

Each row shows the original, then the typography, colour, spacing and layout twins.

![twins](../data/reports/2026-10-03-batch/twins.jpg)

- **Typography, colour and layout twins** are clearly worse than the original.
- **The spacing twin** barely differs from the original, too weak to teach anything.
- **bellussi's twins** all show the age gate, so a gate pollutes every twin too.

### Stills

- Normal pages got four stills from native scrolling.
- Scroll-hijacking pages fell back to wheel scrolling, which worked on heronaiapp, dorot, lekhoa
  and middlename.
- **Full-screen and hijacked pages often got only one or two stills:** limlondon, ot.studio,
  aster, barletta, revolut, robbyyeager, archier, cltv.

### Reels

- They run 15–31 seconds, median about 20.
- **Every reel judders five times a second, whatever the site.** Playwright records at a fixed
  25fps, and our transcode outputs 30fps, so one frame in six is a duplicate. That shows up as 15–115
  frozen frames per reel in the middle of motion.
- Some reels barely move: bellussi and ot.studio (stuck behind gates), robbyyeager, revolut.
- Reels play correctly in Chromium. I tested playback.

### Metrics

- Six sites ignore the reduced-motion setting.
- Dropped-frame ratios of about 0.5 on robbyyeager and lsv-invictus can't yet be trusted. They may
  reflect two browsers running headless at once on this machine, not the site.

### 4b. Re-run after the fixes

The same 30 sites and twins, captured again with capture version 2.1 (all fixes in section 5).
Contact sheets: `data/reports/2026-10-03-rerun/`.

- ![re-run sheet 1](../data/reports/2026-10-03-rerun/sheet-1.jpg)
- ![re-run sheet 2](../data/reports/2026-10-03-rerun/sheet-2.jpg)
- ![re-run sheet 3](../data/reports/2026-10-03-rerun/sheet-3.jpg)
- ![bellussi, now through its gate and cookie dialog](../data/reports/2026-10-03-rerun/bellussi.jpg)
- ![twins](../data/reports/2026-10-03-rerun/twins.jpg)

| Site | First run | Re-run |
|---|---|---|
| bellussi (8) | Passed QA, but every still was the age gate | Cookie dialog accepted ("Accetta tutti"), gate answered ("SI"), four real screens, passes |
| oxigen (21), aralesk (149), illoca (308) | Failed: 2.5 s screenshot timeout | Captured; illoca scrolls an inner element and got four "inner" stills |
| flyward (388) | "Explore" clicked twice, ended on `/private-service` | No gate click; the home page; four stills |
| revolut (683) | Blocked by Cloudflare | Passes: four stills, cookie banner accepted |
| ot.studio (540) | Stuck on the flashing-lights warning, one still | "Okay" clicked; three project slides |
| archier (939) | Two stills | Four: the slideshow gets patient wheel gestures |
| limlondon (531), aster (850) | Passed QA | Flagged parked |
| madeleinedalla (946) | Passed QA | Flagged spam |
| maisonmargiela (638) | Flagged bot block | Flagged site down (Cloudflare 522, as you saw) |
| collection-ii.mfisher (627) | Dead domain | Dead domain (correct) |

**Stills per site:** 20 sites have four. The rest have fewer because the page has fewer, which I
checked in a browser:

- robbyyeager: one screen; nothing scrolls.
- barletta: a one-screen "coming soon" page.
- middlename: 1.4 screens.
- cltv: 1.7 screens.
- dorot: a one-screen timeline.
- ot.studio: a flashing full-screen showcase; its third wheel gesture did not move.

The first run gave some of these four stills by saving animation frames of the same screen as extra
"screens". That would have taught voters and the model that a one-screen site had four.

**Reels:**

- The dropped-frame ratio is now about 0 for every site. The first run's 0.3–0.5 came from WebGL
  rendering in software, so the motion numbers are now trustworthy.
- Judder on plain sites fell from 21–33 frozen frames per reel to 1–6, thanks to Chromium's own
  scroll gesture.
- A reel is capped at 45 s, so a very slow page (lsv-invictus) is cut short instead of stalling.

**Still open:**

- dorot shows its "A short intro before we begin" box: a small centred dialog, not a full-screen
  layer, and the site rewrites its URL as the timeline animates.
- Twins of sites that cycle their own content (ot.studio) catch a different slide from the
  original, so the pair differs by more than the damaged dimension. Proposed fix: capture twin pairs
  with animations paused.

---

## 5. Problems found, by severity

Evidence comes from the first run. **All of A–O were fixed on 3 October and verified by the
re-run (section 4b) and by new browser tests** that copy each failure on a local page: an age gate,
a warning gate in front of a wheel-driven slideshow, an inner scroller, a backdrop "Explore" link,
and a failed transcode.

Extra fixes found during the work:

- Screen comparisons use colour, not grey: two slides of equal brightness looked identical.
- Consent buttons were added in more languages: bellussi's "Accetta tutti".
- The reel scrolls with Chromium's scroll gesture and has a 45 s cap.
- Every metric now reaches the features.

### Must fix before the 100-site run

| # | Problem | Evidence | Proposed fix |
|---|---|---|---|
| A | Every page operation, screenshots included, times out after 2.5s: `browser.py:44` sets the click timeout as the default | 3 of 30 sites failed, every retry included; one site's 4 twins failed too | Keep 2.5s for clicks only; give screenshots and evaluations their own longer timeout |
| B | The browser announces itself as a bot: "HeadlessChrome" in the user agent, and `navigator.webdriver = true` | Revolut returned 403. With a normal user agent and `--disable-blink-features=AutomationControlled` it returned 200, in both bundled Chromium and real Chrome | A user-agent setting that matches the browser version, plus that flag |
| C | The gate-clicker clicks normal links, and same-site navigation goes undetected | flyward ended on `/private-service`; dorot's "Skip" changed the content. Both passed QA | Click only when a large overlay is actually covering the page, and fail QA when the final path differs from the requested one |
| D | Gates in other forms aren't recognised | bellussi's age gate ("NO / SI") and ot.studio's warning ("Okay"); both passed QA with every still showing the gate | Add yes/sì/oui/ja/"I am over 18"/okay/agree for age and warning gates; flag "same image on every still" |
| E | Parked, spam and dead domains pass QA | limlondon, aster, madeleinedalla | A link-health pass before capture (DNS, status, redirect to `/lander`, parked-domain hosts and phrases), and Claude's description flagging "not a real site" |
| F | Every reel judders five times a second | 25fps recorded, 30fps output | Output at 25fps |
| G | Twins also record reels and run the reduced-motion check | Twins took 50–79s each; the full scrape would be about 45 hours instead of about 20 | Twins capture stills only |
| H | A failed transcode throws away a good capture (also review item 6) | Code reading: the ffmpeg error escapes to the generic handler | Catch it and set the `reel_missing` flag instead |

### Should fix soon

| # | Problem | Fix |
|---|---|---|
| I | Motion metrics may measure our machine, not the site: 2 workers, headless | Record reels one at a time; compare headless with real Chrome on 3–5 heavy sites |
| J | Menu detection clicks any collapsed button (language pickers, FAQ toggles); the reel doesn't notice if a click changes the page | Tighter selector, and a same-page check after the click |
| K | The reel waits a fixed 4s for the intro, so a long preloader ends up in the scroll | Wait for content to become visible, as the analysis visit does |
| L | Full-screen sites give one or two stills | Use the wheel fallback longer, or treat "one screen" as valid and say so |
| M | Maison Margiela is flagged "bot block" when it's actually down | Separate "site down" (5xx, or Cloudflare 52x) from "blocked" |
| N | The reduced-motion check counts CSS animations only, not JavaScript motion | Also compare GSAP calls and page changes with and without reduced motion |
| O | The spacing twin is too weak to matter | Stronger spacing profile |

---

## 6. The external code review: verdicts

Each point was checked against the code, and against the test results where possible.

**Fixed on 3 October:**

- 1: gates are clicked only inside a blocking layer, and a page change after load fails QA.
- 2: the leaderboard file was deleted.
- 3: votes faster than 1 s are refused, votes under 3 s count as low effort, and the API returns 429.
- 4: the v1 schema file is marked deprecated.
- 6: a failed transcode keeps the capture.
- 7: adaptive pairing skips a capture the voter has exhausted.
- 9: bad input gives a usage error, not a traceback.
- 13 and 15: the README was rewritten.
- 14: the guide no longer hardcodes counts.
- 18: the voting page shows a loading state.
- 21: tests were added for gates, transcode failure and the runner, and the fake database now filters.
- 22: the batch state file is locked.
- 23: the Python upper bound was removed.

Also fixed: `web/public/README.md`, an old copy of the design doc, was being served publicly. It was
deleted.

| # | Point | Verdict |
|---|---|---|
| 1 | Gate click false positives; same-site navigation undetected | **Real, and confirmed in the test** (flyward). Matching is on the exact label, not a substring, so it's narrower than stated, but the trigger condition is too broad |
| 2 | XSS in `leaderboard.html` | Real, but in a dead v1 file: it calls APIs that no longer exist. Delete it in the cleanup |
| 3 | No rate limit; `min_vote_seconds` never enforced | Real but low for a four-designer, invite-only pilot: every vote needs a served token, and a voter can be switched off. `min_vote_seconds` is unused config: either use it to flag fast votes in the agreement views, or drop it |
| 4 | v1 `supabase_schema.sql` grants anonymous read and write | **Real, and worse than stated: your live database runs this v1 schema, so those policies are probably active now.** Check the dashboard. Archive the file in the cleanup |
| 5 | Reduced motion is "false" for static sites | **Wrong.** The code gives "unknown" when nothing is animating. The real weakness is that it counts CSS animations only (problem N) |
| 6 | A failed transcode destroys good captures | **Real** (problem H) |
| 7 | Adaptive pairing can strand a heavy voter | Real edge case: it picks one capture first and gives up if this voter has paired it with everything. Fix by choosing the pair, not the capture |
| 8 | `batches.collect` hangs forever on cancelled or expired batches | **Mostly wrong.** In the SDK, cancelled and expired batches end with status "ended". The longest wait is the API's 24 hours, and `--no-wait` exists. A timeout is optional |
| 9 | CLI shows raw tracebacks | Real (reproduced). Low: an operator tool, but worth clean messages |
| 10 | API crashes when unpacking empty results | Mostly theoretical: `voting_config` always has exactly one row by constraint, and foreign keys stop served captures from disappearing |
| 11 | `describe` crashes on empty stills | Theoretical: the hero is always taken, or the capture fails |
| 12 | Analysis crashes on missing keys | Low: the input is our own capture output. Validating `dom.json` with a schema would be cleaner |
| 13, 15 | `web/README.md` is an outdated v1 guide | Real. Delete it in the cleanup; `guide.html` is the source of truth |
| 14 | The guide hardcodes "1 to 3" and "1 to 6" | Real, low |
| 16, 19 | Leaderboard styling and pagination | Moot: the file is going |
| 17 | Global state in `app.js` | Opinion; fine for a page this size |
| 18 | No loading state for images | Real, low |
| 20 | Magic numbers in CSS | Nit |
| 21 | Test gaps | **Real:** no tests for gate behaviour, transcode failure or the runner, and the fake Supabase ignores filters, so it can hide bugs |
| 22 | Race on the batch state file | Real, low: only matters with two operators at once |
| 23 | Python pinned below 3.13 | Real, low: the upper bound isn't needed |
| 24 | Flask is a dev-only dependency | **Wrong.** The API is deployed separately, with its own `web/requirements.txt` that includes Flask |

---

## 7. Training: data, method and use

### Data

| Data | Source | Used for |
|---|---|---|
| Four stills per site | capture | image embeddings, then visual scores |
| Motion reel | capture | frame embeddings, then the motion score |
| UX metrics: load, layout shift, dropped frames, scroll hijack, reduced motion | capture | motion and UX inputs |
| Fonts, type scale, palette, spacing; animation list | capture | inputs, and a style guide for designers |
| Pixel and layout features | analysis | inputs, and explaining scores |
| Claude descriptions (facts only) | describe | search and filters; never quality labels |
| Visual and motion votes, with dimensions, reasons and timing | designers | **the real labels** |
| Original beats each degraded twin | automatic | one label per dimension (the typography twin trains the typography head) |
| Award site beats generated page | automatic, generator not built | the "slop" direction; a weaker label |

Each designer's votes are weighted by their reliability in calibration. "Can't decide" and "broken"
votes are left out.

### Method

1. **Baseline first.** Claude Opus 5.5 judges the same pairs, in both orders to catch side bias. That's
   the bar a trained model must beat, and it tells us whether training is worth it.
2. **A pairwise scorer.** A frozen, pretrained image model (SigLIP, CLIP or DINOv2) turns each
   screen into numbers. A small network on top learns a score per site from the votes, using the
   Bradley–Terry model: P(A beats B) = σ(score A − score B). It's the recipe behind PickScore,
   ImageReward and the LAION aesthetic predictor. With about 1,400 pilot votes, training only the part
   on top is the right size.
3. **One head per dimension (MDPD).** Each head trains on the votes that cited its dimension, plus the
   twins. The motion head uses reel frames, UX metrics and animation features.
4. **Honest testing.** Train and test are split by site, never by pair, with fixed seeds. The ceiling
   is how often the designers agree with each other.
5. **Critiques.** Claude writes them from the scores, the measured facts and the human reasons from the
   most similar pairs. Fine-tuning a vision-language model (SFT then DPO, where MADPO could return)
   only makes sense later, if those critiques fall short and enough written reasons exist. The
   earlier runs failed on inputs, labels and testing, not on the loss function.

### Use

- **Designers:**
  - a library ranked by craft, overall and per dimension;
  - filters from the descriptions;
  - each site's tokens as a ready style guide;
  - "more like this" from the embeddings.
- **Coding agents over MCP:** the agent's page is rendered and captured the same way, scored per
  dimension, compared with the nearest award sites, and critiqued. The award-vs-generated direction
  flags drift toward slop.
- **Research:** the agreement numbers show whether taste is learnable before more is spent.

---

## 8. Order of work: 100 sites before 1,000

No training happens on captures alone; the model needs votes. The order I recommend:

1. **Fix problems A–H**, then re-run these same 30 sites to confirm the fixes.
2. **Capture 100 sites**, with a link-health pass first. Review the contact sheets by eye, and track the
   true pass rate, not just the QA flag.
3. **Pilot on those 100.**
   - Pick 14 good, varied sites for calibration: 91 pairs per round, every designer judges all of them.
   - Then adaptive voting across the rest.
4. **Measure.**
   - designer agreement and consistency;
   - the Claude baseline;
   - a first scorer on the pilot votes and twins.
5. **Decide on scale.** If designers agree well enough and the scorer beats chance on held-out sites,
   capture the remaining sites, the twins (stills only) and the generated pages, and keep collecting
   votes.

Going straight to 1,000 would bake today's 25% false-pass rate and 17% link rot into the dataset.

---

## 9. Proposed next steps

Steps 1 and 2 of the original plan (fix and re-run) are done. Waiting for your go-ahead on the rest.

1. The two open capture cases: small onboarding dialogs like dorot's, and twins captured with
   animations paused.
2. A link-health pass over all 1,006 URLs: dead, parked and spam domains are about 17% of the sample.
3. The 100-site capture, then the pilot.
5. Separately, before going live:
   - check the live v1 database for the open anonymous policies (review item 4);
   - apply the v2 migration;
   - archive the v1 files.

---

## 10. How to reproduce

```bash
cd taste-engine
.venv/bin/taste capture --ids 8,21,31,55,112,130,133,149,298,308,349,388,399,490,512,531,540,627,637,638,652,683,777,814,850,864,900,939,946,996
.venv/bin/taste capture --ids 8,21,31 --variants typography,colour,spacing,layout
# Per-site results: data/captures/<id>-<variant>/capture.json
# Summary used above: data/reports/2026-10-03-batch/batch_rows.json

# Tests (the Postgres tests need PG_BIN)
PG_BIN=/opt/homebrew/opt/postgresql@16/bin .venv/bin/python -m pytest -q
```
