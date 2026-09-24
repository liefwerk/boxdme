# boxdMe

Local single-page HTMX app that fetches a public Letterboxd watchlist, enriches each movie with TMDB metadata, stores it in SQLite, and groups it by mood/theme.

## Requirements

- Python 3.11+
- A TMDB API key from <https://www.themoviedb.org/settings/api>

## Setup

1. Copy `.env.example` to `.env`.
2. Set `TMDB_API_KEY` in `.env`.
3. Install dependencies:

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

## Notes

- Only public Letterboxd watchlists are supported.
- The app stores data locally in `boxdme.sqlite3`.
- Re-syncing the same user skips TMDB lookups for movies that already have saved metadata.
