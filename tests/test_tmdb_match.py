from __future__ import annotations

from app.letterboxd_film import parse_tmdb_id_from_film_html
from app.tmdb import _pick_best_match, normalize_title


def test_normalize_title_strips_punctuation() -> None:
    assert normalize_title("Don't Look Up") == "don t look up"
    assert normalize_title("The Matrix") == "the matrix"


def test_parse_tmdb_id_from_track_link() -> None:
    html = """
    <a data-track-action="TMDB"
       href="https://www.themoviedb.org/movie/752/v-for-vendetta">TMDB</a>
    """
    assert parse_tmdb_id_from_film_html(html) == 752


def test_parse_tmdb_id_from_reversed_attributes() -> None:
    html = """
    <a href="https://www.themoviedb.org/movie/27205/inception"
       data-track-action="TMDB">TMDB</a>
    """
    assert parse_tmdb_id_from_film_html(html) == 27205


def test_parse_tmdb_id_missing_returns_none() -> None:
    assert parse_tmdb_id_from_film_html("<html></html>") is None


def test_pick_best_match_requires_title_agreement() -> None:
    results = [
        {"id": 1, "title": "Totally Different", "release_date": "1999-01-01"},
        {"id": 2, "title": "The Matrix", "release_date": "1999-03-31"},
    ]
    match = _pick_best_match(results, "The Matrix", 1999)
    assert match is not None
    assert match["id"] == 2


def test_pick_best_match_rejects_wrong_year() -> None:
    results = [
        {"id": 1, "title": "The Thing", "release_date": "2011-10-14"},
        {"id": 2, "title": "The Thing", "release_date": "1982-06-25"},
    ]
    match = _pick_best_match(results, "The Thing", 1982)
    assert match is not None
    assert match["id"] == 2

    assert _pick_best_match(results, "The Thing", 1951) is None


def test_pick_best_match_rejects_unrelated_top_hit() -> None:
    results = [
        {"id": 99, "title": "Unrelated Blockbuster", "release_date": "2020-01-01"},
    ]
    assert _pick_best_match(results, "Parasite", 2019) is None
