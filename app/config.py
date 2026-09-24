from __future__ import annotations

import os

from app.letterboxd import validate_username


def get_retention_hours() -> int:
    raw = os.getenv("WATCHLIST_RETENTION_HOURS", "24").strip()
    try:
        hours = int(raw)
    except ValueError:
        hours = 24
    return max(1, hours)


def get_persist_username() -> str | None:
    raw = os.getenv("PERSIST_USERNAME", "").strip()
    if not raw:
        return None
    return validate_username(raw)


def is_persisted_user(username: str) -> bool:
    owner = get_persist_username()
    return owner is not None and username == owner


def local_cache_note(retention_hours: int) -> str:
    return (
        f"Saved on this server's disk. Removed if unused for {retention_hours} hours."
    )


def session_cache_note(retention_hours: int) -> str:
    return (
        f"Not saved to disk — processed in memory only, cleared after "
        f"{retention_hours} hours without use."
    )
