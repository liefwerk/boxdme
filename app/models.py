from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FilmStub:
    letterboxd_slug: str
    title: str
    year: int | None
    letterboxd_url: str
    is_tv: bool = False


@dataclass(slots=True)
class EnrichedFilm:
    letterboxd_slug: str
    title: str
    year: int | None
    letterboxd_url: str
    tmdb_id: int | None = None
    poster_url: str | None = None
    mood: str = "Uncategorized"
    sub_mood: str = "General"
    genres: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    letterboxd_avg_rating: float | None = None
    member_rating: float | None = None
    review_excerpt: str | None = None

    @property
    def rating_half_steps(self) -> int:
        """Floor half-star steps for minimum-threshold CSS filters (4★+ means >= 4.0)."""
        if self.letterboxd_avg_rating is None:
            return 0
        return int(self.letterboxd_avg_rating * 2)


@dataclass(slots=True)
class SyncResult:
    username: str
    film_count: int
    last_synced_at: str
    mood_order: list[str]
    grouped_films: dict[str, dict[str, list[EnrichedFilm]]]
    default_sub_moods: dict[str, str]
    unmatched_titles: list[str] = field(default_factory=list)
    skipped_tv_titles: list[str] = field(default_factory=list)
    used_cached_watchlist: bool = False
    skipped_tmdb: bool = False
    refreshed_moods: bool = False
    rated_film_count: int = 0
