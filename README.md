# dziner: the TASTE engine

TASTE learns what well-made web design looks like from designers' judgments. Two audiences use it:

- **Designers:** a library of sites ranked by craft, overall and per dimension.
- **Coding agents (over MCP):** a critic that steers them away from generic "AI default" pages.

## Where things are

| Path | What |
|---|---|
| `AI_Design_Taste_Engine_Brief.md` | The idea and the market; v2's architecture, method, data, biases, limits, alternatives and roadmap |
| `taste_engine_journal.md` | The project journal, by date: v1's journey and why it failed, the v2 rebuild, the pilot |
| `taste-engine/` | The v2 code: the `taste` command line, the voting site, the database schema |
| `taste-engine/docs/operations.md` | Running it live: hosting, free-tier limits, the database history, runbooks |
| `list.md`, `taste-engine/manifest/sites.csv` | The site list and the manifest made from it. Not in the repository (git-ignored): keep them on the capture machine, with a backup elsewhere. The pipeline needs `sites.csv` |

## Quick start

```bash
cd taste-engine
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium
.venv/bin/taste --help
.venv/bin/python -m pytest -q   # the Postgres tests need PG_BIN pointing at Postgres binaries
```

The usual flow is:

1. `taste capture`
2. `taste analyze`
3. `taste publish`
4. `taste calibrate`
5. `taste voters add`
6. Voting.
7. `taste votes agreement` / `taste votes export`

See `taste-engine/docs/operations.md`.
