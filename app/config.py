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
        f"We keep this watchlist on the server so the next load is quicker. "
        f"If you don't come back for {retention_hours} hours, we'll drop it."
    )


def session_cache_note(retention_hours: int) -> str:
    return (
        f"We don't save your watchlist on the server—it's only here while you're browsing. "
        f"After {retention_hours} hours without a visit, it's gone."
    )
