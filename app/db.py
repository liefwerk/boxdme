from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.models import EnrichedFilm

DB_PATH = Path(__file__).resolve().parent.parent / "boxdme.sqlite3"


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                last_synced_at TEXT NOT NULL,
                watchlist_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS films (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                letterboxd_slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                year INTEGER,
                tmdb_id INTEGER,
                poster_url TEXT,
                mood TEXT NOT NULL,
                genres_json TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                letterboxd_url TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_films (
                username TEXT NOT NULL,
                letterboxd_slug TEXT NOT NULL,
                PRIMARY KEY (username, letterboxd_slug),
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
                FOREIGN KEY (letterboxd_slug) REFERENCES films(letterboxd_slug) ON DELETE CASCADE
            );
            """
        )
        _ensure_users_watchlist_hash_column(connection)
        _ensure_user_films_member_columns(connection)
        _ensure_films_extra_columns(connection)


def _ensure_user_films_member_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(user_films)").fetchall()
    }
    if "member_rating" not in columns:
        connection.execute("ALTER TABLE user_films ADD COLUMN member_rating REAL")
    if "review_excerpt" not in columns:
        connection.execute("ALTER TABLE user_films ADD COLUMN review_excerpt TEXT")


def _ensure_films_extra_columns(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(films)").fetchall()
    }
    if "sub_mood" not in columns:
        connection.execute("ALTER TABLE films ADD COLUMN sub_mood TEXT NOT NULL DEFAULT 'General'")
    if "letterboxd_avg_rating" not in columns:
        connection.execute("ALTER TABLE films ADD COLUMN letterboxd_avg_rating REAL")


def _ensure_users_watchlist_hash_column(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "watchlist_hash" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN watchlist_hash TEXT")


@contextmanager
def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def get_cached_film(letterboxd_slug: str) -> EnrichedFilm | None:
    return get_cached_films([letterboxd_slug]).get(letterboxd_slug)


def get_cached_films(letterboxd_slugs: list[str]) -> dict[str, EnrichedFilm]:
    if not letterboxd_slugs:
        return {}

    placeholders = ", ".join("?" for _ in letterboxd_slugs)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                letterboxd_slug,
                title,
                year,
                tmdb_id,
                poster_url,
                mood,
                sub_mood,
                letterboxd_avg_rating,
                genres_json,
                keywords_json,
                letterboxd_url
            FROM films
            WHERE letterboxd_slug IN ({placeholders})
            """,
            tuple(letterboxd_slugs),
        ).fetchall()

    cached: dict[str, EnrichedFilm] = {}
    for row in rows:
        cached[row["letterboxd_slug"]] = EnrichedFilm(
            letterboxd_slug=row["letterboxd_slug"],
            title=row["title"],
            year=row["year"],
            tmdb_id=row["tmdb_id"],
            poster_url=row["poster_url"],
            mood=row["mood"],
            sub_mood=row["sub_mood"] or "General",
            letterboxd_avg_rating=row["letterboxd_avg_rating"],
            genres=json.loads(row["genres_json"]),
            keywords=json.loads(row["keywords_json"]),
            letterboxd_url=row["letterboxd_url"],
        )

    return cached


def get_user_watchlist_hash(username: str) -> str | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT watchlist_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not row["watchlist_hash"]:
        return None
    return str(row["watchlist_hash"])


def set_user_watchlist_hash(username: str, watchlist_hash: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET watchlist_hash = ?
            WHERE username = ?
            """,
            (watchlist_hash, username),
        )


def touch_user_last_synced(username: str) -> str:
    synced_at = datetime.now(UTC).isoformat(timespec="seconds")
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (username, last_synced_at)
            VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET last_synced_at = excluded.last_synced_at
            """,
            (username, synced_at),
        )
    return synced_at


def get_user_film_slugs(username: str) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT letterboxd_slug
            FROM user_films
            WHERE username = ?
            ORDER BY letterboxd_slug COLLATE NOCASE ASC
            """,
            (username,),
        ).fetchall()
    return [str(row["letterboxd_slug"]) for row in rows]


def count_member_ratings(username: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS rated_count
            FROM user_films
            WHERE username = ? AND member_rating IS NOT NULL
            """,
            (username,),
        ).fetchone()
        return int(row["rated_count"]) if row else 0


def user_has_member_ratings(username: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM user_films
            WHERE username = ? AND member_rating IS NOT NULL
            LIMIT 1
            """,
            (username,),
        ).fetchone()
        return row is not None


def user_has_cached_watchlist(username: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM user_films WHERE username = ? LIMIT 1",
            (username,),
        ).fetchone()
    return row is not None


def replace_user_watchlist(
    username: str,
    films: list[EnrichedFilm],
    *,
    watchlist_hash: str | None = None,
) -> str:
    synced_at = datetime.now(UTC).isoformat(timespec="seconds")

    with get_connection() as connection:
        if watchlist_hash is None:
            connection.execute(
                """
                INSERT INTO users (username, last_synced_at)
                VALUES (?, ?)
                ON CONFLICT(username) DO UPDATE SET last_synced_at = excluded.last_synced_at
                """,
                (username, synced_at),
            )
        else:
            connection.execute(
                """
                INSERT INTO users (username, last_synced_at, watchlist_hash)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    last_synced_at = excluded.last_synced_at,
                    watchlist_hash = excluded.watchlist_hash
                """,
                (username, synced_at, watchlist_hash),
            )
        connection.execute("DELETE FROM user_films WHERE username = ?", (username,))

        for film in films:
            connection.execute(
                """
                INSERT INTO films (
                    letterboxd_slug,
                    title,
                    year,
                    tmdb_id,
                    poster_url,
                    mood,
                    sub_mood,
                    letterboxd_avg_rating,
                    genres_json,
                    keywords_json,
                    letterboxd_url,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(letterboxd_slug) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    tmdb_id = excluded.tmdb_id,
                    poster_url = excluded.poster_url,
                    mood = excluded.mood,
                    sub_mood = excluded.sub_mood,
                    letterboxd_avg_rating = COALESCE(excluded.letterboxd_avg_rating, films.letterboxd_avg_rating),
                    genres_json = excluded.genres_json,
                    keywords_json = excluded.keywords_json,
                    letterboxd_url = excluded.letterboxd_url,
                    updated_at = excluded.updated_at
                """,
                (
                    film.letterboxd_slug,
                    film.title,
                    film.year,
                    film.tmdb_id,
                    film.poster_url,
                    film.mood,
                    film.sub_mood,
                    film.letterboxd_avg_rating,
                    json.dumps(film.genres),
                    json.dumps(film.keywords),
                    film.letterboxd_url,
                    synced_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO user_films (username, letterboxd_slug)
                VALUES (?, ?)
                ON CONFLICT(username, letterboxd_slug) DO NOTHING
                """,
                (username, film.letterboxd_slug),
            )

    return synced_at


def update_member_fields_for_slugs(
    username: str,
    slugs: list[str],
    activity: dict[str, tuple[float | None, str | None]],
) -> None:
    if not slugs:
        return

    with get_connection() as connection:
        for slug in slugs:
            if slug not in activity:
                continue
            rating, review = activity[slug]
            if rating is None and not review:
                continue
            connection.execute(
                """
                UPDATE user_films
                SET
                    member_rating = COALESCE(?, member_rating),
                    review_excerpt = COALESCE(?, review_excerpt)
                WHERE username = ? AND letterboxd_slug = ?
                """,
                (rating, review, username, slug),
            )


def _row_to_film(row: sqlite3.Row) -> EnrichedFilm:
    return EnrichedFilm(
        letterboxd_slug=row["letterboxd_slug"],
        title=row["title"],
        year=row["year"],
        tmdb_id=row["tmdb_id"],
        poster_url=row["poster_url"],
        mood=row["mood"],
        sub_mood=row["sub_mood"] or "General",
        letterboxd_avg_rating=row["letterboxd_avg_rating"],
        genres=json.loads(row["genres_json"]),
        keywords=json.loads(row["keywords_json"]),
        letterboxd_url=row["letterboxd_url"],
    )


def get_films_for_user(username: str) -> list[EnrichedFilm]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                f.letterboxd_slug,
                f.title,
                f.year,
                f.tmdb_id,
                f.poster_url,
                f.mood,
                f.sub_mood,
                f.letterboxd_avg_rating,
                f.genres_json,
                f.keywords_json,
                f.letterboxd_url
            FROM films f
            INNER JOIN user_films uf ON uf.letterboxd_slug = f.letterboxd_slug
            WHERE uf.username = ?
            ORDER BY f.title COLLATE NOCASE ASC
            """,
            (username,),
        ).fetchall()
    return [_row_to_film(row) for row in rows]


def get_grouped_films_for_user(username: str) -> dict[str, dict[str, list[EnrichedFilm]]]:
    grouped: dict[str, dict[str, list[EnrichedFilm]]] = {}
    for film in get_films_for_user(username):
        grouped.setdefault(film.mood, {}).setdefault(film.sub_mood, []).append(film)
    return grouped


def get_letterboxd_ratings_for_slugs(slugs: list[str]) -> dict[str, float | None]:
    if not slugs:
        return {}
    placeholders = ", ".join("?" for _ in slugs)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT letterboxd_slug, letterboxd_avg_rating
            FROM films
            WHERE letterboxd_slug IN ({placeholders})
            """,
            tuple(slugs),
        ).fetchall()
    return {str(row["letterboxd_slug"]): row["letterboxd_avg_rating"] for row in rows}


def update_letterboxd_avg_ratings(ratings: dict[str, float | None]) -> None:
    if not ratings:
        return
    synced_at = datetime.now(UTC).isoformat(timespec="seconds")
    with get_connection() as connection:
        for slug, rating in ratings.items():
            if rating is None:
                continue
            connection.execute(
                """
                UPDATE films
                SET letterboxd_avg_rating = ?, updated_at = ?
                WHERE letterboxd_slug = ?
                """,
                (rating, synced_at, slug),
            )


def purge_stale_watchlists(*, retention_hours: int = 24) -> tuple[int, int]:
    from datetime import timedelta

    cutoff = (datetime.now(UTC) - timedelta(hours=retention_hours)).isoformat(timespec="seconds")
    users_deleted = 0
    films_deleted = 0

    with get_connection() as connection:
        users_deleted = connection.execute(
            "DELETE FROM users WHERE last_synced_at < ?",
            (cutoff,),
        ).rowcount
        films_deleted = connection.execute(
            """
            DELETE FROM films
            WHERE letterboxd_slug NOT IN (SELECT letterboxd_slug FROM user_films)
            """
        ).rowcount

    if users_deleted > 0 or films_deleted > 0:
        vacuum_connection = sqlite3.connect(DB_PATH)
        try:
            vacuum_connection.execute("VACUUM")
        finally:
            vacuum_connection.close()

    return max(users_deleted, 0), max(films_deleted, 0)


def reclassify_films_for_user(username: str) -> None:
    from app.mood import classify_film

    films = get_films_for_user(username)
    synced_at = datetime.now(UTC).isoformat(timespec="seconds")
    with get_connection() as connection:
        for film in films:
            mood, sub_mood = classify_film(film.genres, film.keywords)
            connection.execute(
                """
                UPDATE films
                SET mood = ?, sub_mood = ?, updated_at = ?
                WHERE letterboxd_slug = ?
                """,
                (mood, sub_mood, synced_at, film.letterboxd_slug),
            )
