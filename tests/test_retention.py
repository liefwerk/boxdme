from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import db
from app.models import EnrichedFilm


def _film(slug: str) -> EnrichedFilm:
    return EnrichedFilm(
        letterboxd_slug=slug,
        title=slug.title(),
        year=2000,
        tmdb_id=None,
        poster_url=None,
        mood="Cozy",
        sub_mood="General",
        letterboxd_avg_rating=None,
        genres=[],
        keywords=[],
        letterboxd_url=f"https://letterboxd.com/film/{slug}/",
    )


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    db.init_db()
    return db


def _age_user(username: str, hours: int) -> None:
    old = (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with db.get_connection() as connection:
        connection.execute(
            "UPDATE users SET last_synced_at = ? WHERE username = ?",
            (old, username),
        )


def test_purge_keeps_persisted_user_indefinitely(temp_db):
    db.replace_user_watchlist("liefwerk", [_film("owner-film")])
    db.replace_user_watchlist("someoneelse", [_film("other-film")])
    _age_user("liefwerk", 24 * 365)
    _age_user("someoneelse", 48)

    users_deleted, films_deleted = db.purge_stale_watchlists(
        retention_hours=24,
        keep_username="liefwerk",
    )

    assert users_deleted == 1
    assert films_deleted == 1
    assert [f.letterboxd_slug for f in db.get_films_for_user("liefwerk")] == ["owner-film"]
    assert db.get_films_for_user("someoneelse") == []


def test_purge_without_keep_username_still_expires(temp_db):
    db.replace_user_watchlist("liefwerk", [_film("owner-film")])
    _age_user("liefwerk", 48)

    db.purge_stale_watchlists(retention_hours=24, keep_username=None)

    assert db.get_films_for_user("liefwerk") == []
