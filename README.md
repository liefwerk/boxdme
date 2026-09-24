# boxdMe

Local single-page HTMX app that fetches a public Letterboxd watchlist, enriches each movie with TMDB metadata, and groups it by mood/theme.

## Requirements

- Python 3.11+
- A TMDB API key from <https://www.themoviedb.org/settings/api>

## Setup

1. Copy `.env.example` to `.env`.
2. Set `TMDB_API_KEY` in `.env`.
3. Optional: set `PERSIST_USERNAME` to your Letterboxd username if you want your watchlist saved to disk.
4. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

## Storage and privacy

| Variable | Default | Meaning |
|----------|---------|---------|
| `PERSIST_USERNAME` | (empty) | If set, only this Letterboxd username is written to `boxdme.sqlite3`. |
| `WATCHLIST_RETENTION_HOURS` | `24` | Inactivity window before purging persisted and in-memory watchlists. |

- **Owner (`PERSIST_USERNAME`)**: watchlist and links are stored in SQLite. Stale owner rows, orphan film metadata, and the DB file are cleaned up (including `VACUUM`) after the retention window without use.
- **Everyone else**: watchlists live **in server memory only** (not written to `users` / `user_films`). Entries are dropped after the same retention window without a sync. TMDB metadata already on disk from the owner may be **read** to speed up enrichment; guest syncs do not write new rows.
- If `PERSIST_USERNAME` is empty, **no** watchlist is persisted to disk (all usernames are session-only).

The UI labels each result as **Local cache** or **Session only**.

**Multi-worker note:** session cache is per process. Running multiple uvicorn workers without sticky sessions means guests may not hit the same memory between requests.

## Notes

- Only public Letterboxd watchlists are supported.
- Re-syncing the same user skips TMDB lookups when cached metadata is still valid.
