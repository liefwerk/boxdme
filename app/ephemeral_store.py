from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.models import EnrichedFilm


@dataclass(slots=True)
class EphemeralWatchlist:
    watchlist_hash: str | None
    enriched_films: list[EnrichedFilm]
    last_synced_at: str
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.last_accessed_at = datetime.now(UTC)


_store: dict[str, EphemeralWatchlist] = {}


def get(username: str) -> EphemeralWatchlist | None:
    return _store.get(username)


def put(
    username: str,
    *,
    watchlist_hash: str | None,
    enriched_films: list[EnrichedFilm],
    last_synced_at: str,
) -> EphemeralWatchlist:
    entry = EphemeralWatchlist(
        watchlist_hash=watchlist_hash,
        enriched_films=enriched_films,
        last_synced_at=last_synced_at,
    )
    _store[username] = entry
    return entry


def touch(username: str) -> None:
    entry = _store.get(username)
    if entry is not None:
        entry.touch()


def has_watchlist(username: str) -> bool:
    entry = _store.get(username)
    return entry is not None and bool(entry.enriched_films)


def purge_inactive(*, retention_hours: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=retention_hours)
    expired = [name for name, entry in _store.items() if entry.last_accessed_at < cutoff]
    for name in expired:
        del _store[name]
    return len(expired)
