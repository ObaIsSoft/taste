# Operations: running TASTE v2 live

How the live system is set up, what the free tiers allow, and the procedures for the database:
the v1 flush, the cutover, smoke tests, voters, exports and recovery. Every database change
that removes data is recorded under [Database history](#database-history).

## Where things run

| Piece | Where | Notes |
|---|---|---|
| Database and media | Supabase project (free tier) | Postgres holds the voting rules; media is in the private bucket `captures` |
| Voting site | Vercel project `taste` (Hobby), deployed from `taste-engine/web` | Production: https://taste-opal.vercel.app. The project is also connected to GitHub and deploys on pushes to `main` |
| Capture, analysis, publishing | This machine | The `taste` command line in `taste-engine/` |
| Site list, manifest, v1 archive | This machine only | `list.md`, `taste-engine/manifest/sites.csv` and `taste-engine/data_v1_archive/` are git-ignored and not in the repository's history. Keep a backup elsewhere; the pipeline needs `sites.csv` |

## Settings

| Where | Variable | Purpose |
|---|---|---|
| `taste-engine/.env` | `SUPABASE_URL` | The Supabase project |
| `taste-engine/.env` | `SUPABASE_KEY` (or `SUPABASE_SERVICE_KEY`) | A Supabase secret key (`sb_secret_…`) for publishing, voters and exports. The legacy JWT keys are disabled; never re-enable them |
| `taste-engine/.env` | `SUPABASE_DB_URL` | Postgres connection string; only needed to apply migrations |
| `taste-engine/.env` | `TASTE_VOTING_URL` | `https://taste-opal.vercel.app`, so `taste voters add/list` print invite links |
| `taste-engine/.env` | `ANTHROPIC_API_KEY` | Claude descriptions and, later, the baseline judge |
| `taste-engine/.env` | `TASTE_PUBLISH_REQUIRES_DESCRIPTION` | `false` while the API account has no credit: publishing then skips Claude's check (see [Publishing without Claude's check](#publishing-without-claudes-check)) |
| Vercel (Production) | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | The API's database access. The service key never reaches a browser |
| Vercel (Production) | `TASTE_STORAGE_BUCKET` | `captures` |
| Vercel (Production) | `TASTE_SIGNED_URL_SECONDS` | Optional; how long media links last (default 3600) |

## Free-tier limits

The project stays on free tiers. What that means in practice:

- **Storage, 1 GB.** A votable site takes about 1 MB: four stills (about 0.56 MB) and a reel (about
  0.45 MB at 960 px wide). That is room for about 1,000 sites. Only originals that passed QA are
  published; twins and failures stay on this machine.
- **Egress, 5 GB a month.** A visual vote loads about 1.1 MB (two sites' stills), and a motion vote
  about 1 MB (two reels, plus posters). The pilot's 1,600 or so votes come to about 2 GB.
- **Database, 500 MB.** A vote is under 1 KB; no concern.
- **Pausing.** Free projects pause after 7 days without requests. Between voting phases, open the
  site or run `taste voters list` at least weekly; a paused project is restored from the
  Supabase dashboard.
- **No automatic backups.** During voting, export after each voting day (see [Exports](#exports)).
- **Vercel Hobby** is ample for a handful of designers.

## Database history

Append an entry for every change that deletes or rewrites data.

### 2026-10-03: v1 flushed, v2 schema applied

- **Why.** v2 is a fresh start: v1 votes came from one person, were made against different captures,
  and do not tie a vote to a voter.
- **Backed up first.** `match_history` and `ratings` were exported to
  `taste-engine/data_v1_archive/supabase/` (on the capture machine only, not in the repository),
  with their schema in `v1_schema.sql`: 771 `match_history` rows and 99 `ratings` rows, matching
  the live tables. There was no `voters` table and no storage bucket.
- **What was dropped.** The v1 tables `match_history` and `ratings`, by
  `supabase/migrations/0001_v2_voting.sql`. Their open anonymous policies went with them.
- **What was created.** The v2 voting schema: 10 tables, 11 views, 12 dimensions, round
  targets (visual 200, motion 100). Checked after: every table has row-level security, and the
  `anon` and `authenticated` roles reach no table, view or function.
- **Restore v1 if ever needed.** Run `v1_schema.sql` in a separate Supabase project (it opens
  tables to anonymous writes, so never in this one), then load the exported JSON.

### 2026-10-03: pilot published and calibration set

- **Published.** The 90 pilot captures that passed QA (capture 2.3.0, analysis 2.1.0), 423 files,
  99 MB. Claude's check was off (`TASTE_PUBLISH_REQUIRES_DESCRIPTION=false`: no API credit), so
  every still was checked by eye against the same rule.
- **Excluded by that check** (`in_pool` false, reason in `qa_note`): 0230 (sign-up pop-up on the
  last still), 0234 and 0680 (discount pop-ups on every still), 0349 (intro dialog), 0733
  (location selector), 0900 (under construction). 84 captures are in the pool, all with reels.
- **Calibration**, picked by `taste calibrate --pick` from the 84:
  - visual, 14 sites, 91 pairs: 133, 224, 271, 284, 292, 298, 348, 382, 446, 625, 747, 814, 939, 949;
  - motion, 8 of those, 28 pairs: 133, 224, 271, 284, 382, 625, 814, 939.
- **Smoke test.** Voter `smoke-test` cast 6 visual votes on a desktop, 1 motion vote and 1 phone
  vote on the live site; all were recorded with their `client` details and events. Then all of
  it was deleted with the SQL in the runbook: 5 events, 8 votes, 10 served pairs, 1 voter.
- **Voters added.** Leonardo, Michelangelo, Raphael, Donatello, Obafemi, Frida. Their links are
  printed by `taste voters list`.
- **Vercel.** `main` fast-forwarded to `v2-rebuild` and deployed. The v1 `SUPABASE_KEY` variable was
  removed; the API reads `SUPABASE_SERVICE_KEY`.

### 2026-10-04: active time (migration 0002), no data changed

- **Why.** `seconds_to_vote` is wall-clock time: a tab left open overnight showed as a 12-hour vote.
  The voting page now sends, with each vote, how long the pair was on screen and in use.
- **What changed.** `voting_config` gained `idle_cutoff_seconds` (120) and `session_gap_minutes`
  (30); `voting_facts()` returns the cut-off to the page; `voter_effort`, `vote_attention` and
  `voter_bias` gained columns at their end. No row was changed or removed.
- **Votes before it** (Obafemi's first 29) had no timing; see the next entry.
- **Checked live.** Rehearsed with a rollback first, then applied. A `smoke-test` voter cast one
  vote with 5 s in another tab (wall-clock 12.4 s, on screen 6.2 s, left the page once); its 1
  vote, 1 served pair and the voter were then deleted with the runbook SQL.

### 2026-10-04: active time for the votes cast before it was measured

- **Why.** Obafemi's first 29 votes predate migration 0002 and had no `client.timing`. At Obafemi's
  request their wall-clock time stands as their active time, except one vote cast after its tab
  was left open overnight.
- **What changed.** `votes.client` gained a `timing` object on those 29 votes, nothing else:
  - 28 votes (ids 9–37 except 23): `active_s`, `focused_s` and `visible_s` set to their
    `seconds_to_vote`, with `"source": "wall_clock"` so analysis can tell them from measured time.
    They have no `away_count`, so whether the voter left the page is unknown (null).
  - Vote 23 (44,712 s, 12.4 hours): `"source": "none"` and a note; no active time.
- **Backed up first** to `data/votes/backup-2026-10-04-before-timing-backfill.json` (git-ignored;
  each vote's `client` as it was).
- **To undo,** remove the key: `update votes set client = client - 'timing'
  where client -> 'timing' ->> 'source' in ('wall_clock', 'none');`

### 2026-10-04: votes pinned to the exact media they showed (migrations 0003, 0004)

- **Why.** A vote named only a capture id, and publishing again overwrote media under the same
  paths, so a re-capture would have silently changed what old votes point at.
- **Backed up first.** `taste votes export`, kept as `data/votes/votes-2026-10-04-1906.jsonl` and
  `vote_events-2026-10-04-1906.jsonl` (29 votes, 60 events).
- **Checked first.** All 423 files in storage were byte-identical (md5) to the local files, so the
  votes already cast could be pinned truthfully to a fingerprint of the local files.
- **What changed.** 0003 (rehearsed with a rollback, then applied) added `capture_media` (every
  published version, append-only), `captures.media_id`, `left_media`/`right_media` on served
  pairs and votes (filled when a pair is served, then fixed), and rules that a site's URL and a
  capture's site never change. All 90 pilot captures were then published again as versions under
  their fingerprints (`<capture>/<media_id>/<file>`); all 423 version files were checked in
  storage against their recorded sha256 and md5. 0004 (rehearsed, then applied) pinned the 36
  pairs served and 29 votes cast before it to those versions and made pins required.
- **Left in storage.** The files from before, at `<capture>/<file>`, are no longer referenced
  (about 99 MB). They can be deleted later to free space; nothing points at them.

### 2026-10-04: a voter given feedback on their own votes (no data changed)

- **What happened.** During voting, Claude told Obafemi (a voter) about their own voting pattern,
  which voters are not otherwise shown:
  - **about 12:00 UTC:** in their cross-kind votes, showcase sites had won 6 and lost 4.
  - **about 19:35 UTC:** they favoured airy, photographic sites; Oxide had won 0 of 7;
    Claude's own judgments disagreed with theirs on 15 of 24 pairs.
- **Votes affected.** Votes 32–37 (12:10–12:21 UTC) were cast after the first feedback. Every
  Obafemi vote after 19:35 UTC follows the second.
- **How to treat it.** Analysis compares Obafemi's votes before and after these times, and reports
  them separately if they differ. Claude's in-session judgments are kept outside the database
  (`data/benchmark/claude-visual-calibration-2026-10-04.jsonl`). They are exploratory, not the
  benchmark: they were made with the project's context and earlier verdicts in view.

### 2026-10-05: keys replaced, repository made public (no data changed)

- **Why.** A full scan before going public found, in old commits, a committed `.env` with the live
  service-role key and a Supabase access token, and a Google API key.
- **Done.** A new secret key (`sb_secret_…`) in `.env` and in Vercel's `SUPABASE_SERVICE_KEY`,
  with the live site tested on it. Then:
  - the legacy JWT keys disabled; the leaked service-role key now returns 401;
  - the access token revoked;
  - the Google key deleted;
  - the database password reset.

  The history was rewritten to remove the keys, the site list, the manifest and the v1 archive,
  and the repository was made public.
- **Still reachable.** GitHub can still serve the pre-rewrite commits to anyone who knows their
  ids, until GitHub Support purges them. The keys in them are dead; the site list and the v1
  media are not secret, but are kept out of the repository.

### 2026-10-05: calibration in a balanced order (migration 0005, no data changed)

- **Why.** Calibration pairs came in a random order per voter, and random is not even. After 43
  votes Obafemi had seen Oxide 10 times and Permian twice, and sites often came up in back-to-back
  pairs: a source of fatigue.
- **What changed.** `next_pair` now serves the calibration pair whose sites the voter has seen
  least, avoiding a site from their previous pair. The set of pairs is unchanged, so votes before
  and after stay comparable. In a simulation of four voters, the worst gap between the most- and
  least-shown site fell from 7–8 to 2, and back-to-back repeats from 20–27 per voter to none.
- **Checked.** Rehearsed with a rollback, applied, then a temporary voter's four live pairs showed
  eight different sites; that voter was deleted.
- **Votes before it.** Obafemi's first 43 and Michelangelo's first 6 calibration votes followed the
  random order. Their remaining pairs now come in the balanced order, which evens out their
  exposure as far as the pairs left allow.

### 2026-10-05: a calibration site reported broken, then reinstated

- **What happened.** At 20:46 UTC Leonardo, on a 360-pixel phone, reported 348 (reimaginegenesis.com)
  as broken, 13 seconds into the pair, without opening that site's screens. A report takes a capture
  out of the pool for everyone, so the visual calibration set fell from 14 sites (91 pairs) to 13
  (78).
- **Why it was reinstated.** The capture is genuine: a dark, scroll-animated site that reads as
  nearly blank on a small screen. Obafemi had judged 8 of its pairs without a problem. At 21:48 UTC
  `in_pool` was set back to true and `qa_note` cleared: calibration is 14 sites and 91 pairs again.
- **Kept.** Leonardo's report stays as a vote (`broken_left`, vote 72). Its pair (348 against 625)
  counts as done for Leonardo, so that one calibration pair has no verdict from them.
- **The weakness.** A single report changes the calibration set for every voter at once.

## Runbooks

### Cutover from v1 to v2 (one window)

v1's site breaks the moment its tables are dropped, so these run back to back.

1. **Export v1.** Use the snippet in [Exporting v1](#exporting-v1). Check that the row counts match
   the live tables.
2. **Apply the schema.** From `taste-engine/`, run each file in `supabase/migrations/` in order:
   `set -a; . ./.env; set +a; psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/0001_v2_voting.sql`,
   then `0002_active_time.sql` and `0003_pinned_media.sql`, or paste them into the Supabase SQL
   editor. `0004_require_pinned_media.sql` comes after the first publish (step 3), then
   `0005_balanced_calibration_order.sql`.
3. **Check and publish the pilot.** Each step runs on every site the same way; there are no
   per-site exceptions:
   - `taste analyze --ids "$(cat manifest/pilot-ids.txt)"`
   - `taste describe --ids "$(cat manifest/pilot-ids.txt)"`. This is Claude's check: it looks at
     every still and reports anything covering the page, and whether the page is a live site.
     Without API credit, see [Publishing without Claude's check](#publishing-without-claudes-check).
   - `taste publish --ids "$(cat manifest/pilot-ids.txt)"`. It only publishes captures that passed
     QA and that Claude saw as clean, and it creates the private bucket on first run.
4. **Set calibration.** The sites are picked automatically as the most varied voteable ones:
   - `taste calibrate --round visual --pick 14`
   - `taste calibrate --round motion --pick 8 --ids <the visual picks>`, so the motion sites are
     a subset of the visual ones. `--pick` prints its choice in `--ids` form for this.
   - Add `--dry-run` to see the picks first. Record the chosen ids in the database history.
5. **Configure Vercel.** Set the Production variables listed above, then from `taste-engine/web` run
   `vercel --prod`.
6. **Smoke test** (below).
7. **Add the designers.** `taste voters add "Name"` for each, and send each their invite link
   privately.

### Publishing without Claude's check

Claude's check needs API credit. Without it, set `TASTE_PUBLISH_REQUIRES_DESCRIPTION=false` in
`.env`: every capture that passed QA is published, and a person does the check instead.

1. Make contact sheets of every votable capture's stills and look at each one, applying Claude's
   rule: nothing covering the page that a visitor would have to dismiss, and a live site (not
   under construction, closed or for sale).
2. Publish, then take each failing capture out with
   `taste captures exclude <id> --reason "..."`. Do this before picking calibration sites;
   `--pick` only chooses from captures still in the pool.
3. Record the excluded ids and reasons in the database history.

To turn the check back on, add credit, remove the line from `.env`, run `taste describe` on the
published ids, and publish again. Captures Claude sees as covered then stay local on later
publishes, but a capture already in the pool stays there until it is excluded.

### Smoke test, and removing its data

1. `taste voters add smoke-test`, then open the printed invite link.
2. Cast a few votes in each round: one with listed dimensions, one with your own words, one
   "Equally good". Do not use **Report**, which takes a capture out of the pool.
3. Remove every trace in the SQL editor:

```sql
with v as (select id from voters where name = 'smoke-test')
delete from vote_events where token in (select token from served_pairs where voter_id in (select id from v));
with v as (select id from voters where name = 'smoke-test')
delete from votes where voter_id in (select id from v);
with v as (select id from voters where name = 'smoke-test')
delete from served_pairs where voter_id in (select id from v);
delete from voters where name = 'smoke-test';
```

4. Record the smoke test and its removal in the database history.

### Voters

- **Add a voter:** `taste voters add "Name"` prints their code and invite link.
- **Re-send a lost link:** `taste voters list`.
- **Switch a voter off:** `taste voters disable "Name"`. Their votes stay; their code stops working.

### During voting

- **Daily:** `taste votes agreement`. Watch these:
  - panel agreement on calibration pairs;
  - each designer's consistency on repeats;
  - fast votes;
  - visual and motion splits.
- **Pilot votes are real data.** Never flush them. They carry into the full run.
- **Do not change the dimension list or the calibration sites during a phase.** Votes before and
  after would not be comparable; designers' own words already catch anything the list misses.
- **Re-capturing a site publishes a new version of its media; it never replaces the old one.**
  `taste publish` names each version by a fingerprint of its files, uploads them under it, and
  records it in `capture_media`. Pairs served from then on show the new version; every pair and
  vote served before keeps pointing at the version it showed (`left_media`, `right_media`), whose
  files stay in storage. Note the re-capture in the database history.
- **A site id always means the same URL.** The database refuses to change a site's URL, and
  publish refuses a capture whose URL is not its site's.
- **Take a capture out of the pool:** `taste captures exclude 0234-original --reason "..."`. The
  reason is kept in its `qa_note`, which keeps it out on later publishes; votes already cast stay.

### Exports

- **Every vote, plus which reels were played and which live sites opened:**
  `taste votes export` writes `data/votes/votes.jsonl` and `vote_events.jsonl`, and with them what
  the votes point at: `capture_media.jsonl` (each media version, its files and their hashes) and
  `sites.jsonl` (each site id's URL). The files are git-ignored; copy them somewhere safe.
- **After each voting day,** run it by hand, and keep a dated copy (each export overwrites the
  last). It is a backup, not the final dataset, which can be rebuilt from any complete export.
  There are no automatic backups on the free tier, and no scheduled export is set up.

### Exporting v1

Run once, before the cutover, from `taste-engine/`:

```python
import json
from pathlib import Path
from taste_engine import db
from taste_engine.settings import get_settings

client = db.connect(get_settings())
out = Path("data_v1_archive/supabase")
for table, order in (("match_history", ("id",)), ("ratings", ("site_id",))):
    rows = db.select_all(client, table, order)
    (out / f"{table}.json").write_text(json.dumps(rows, indent=1))
    print(table, len(rows))
```
