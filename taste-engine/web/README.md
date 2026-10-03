# Voting app

The voting site for the TASTE engine: a thin Flask API (`api/index.py`) and static pages
(`public/`), deployed on Vercel. Every voting rule lives in Postgres, in
`../supabase/migrations/0001_v2_voting.sql`; the API checks the invite code, calls those
functions, signs short-lived media links and turns database errors into HTTP status codes.

The voter guide is `public/guide.html`, served at `/guide.html`. It is the only voter guide.

## Environment

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | The Supabase project |
| `SUPABASE_SERVICE_KEY` | The service key. Server side only; it never reaches a browser |
| `TASTE_STORAGE_BUCKET` | The private bucket with the stills and reels, e.g. `captures` |
| `TASTE_SIGNED_URL_SECONDS` | Optional: how long media links stay valid (default 3600) |

`requirements.txt` here is what Vercel installs for the API.

## Run it locally

```bash
cd taste-engine
SUPABASE_URL=... SUPABASE_SERVICE_KEY=... TASTE_STORAGE_BUCKET=captures \
  .venv/bin/python web/api/index.py   # http://127.0.0.1:5001
```

## Invite voters

`taste voters add "Name"` prints an invite code, and an invite link that signs the voter in
when `TASTE_VOTING_URL` is set.
