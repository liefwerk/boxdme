from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import (
    get_cached_films,
    get_grouped_films_for_user,
    get_letterboxd_ratings_for_slugs,
    get_user_film_slugs,
    get_user_watchlist_hash,
    init_db,
    reclassify_films_for_user,
    replace_user_watchlist,
    set_user_watchlist_hash,
    touch_user_last_synced,
    update_letterboxd_avg_ratings,
    user_has_cached_watchlist,
)
from app.letterboxd import InvalidUsernameError, LetterboxdError, WatchlistEmptyError, fetch_watchlist, validate_username
from app.letterboxd_film import fetch_missing_average_ratings
from app.models import EnrichedFilm, FilmStub, SyncResult
from app.mood import MOOD_ORDER, classify_film, default_sub_mood, mood_meta, mood_slug
from app.tmdb import TmdbError, enrich_film
from app.watchlist_hash import compute_watchlist_hash, compute_watchlist_hash_from_slugs

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["mood_slug"] = mood_slug
templates.env.globals["mood_meta"] = mood_meta


def _format_stars(rating: float | None) -> str:
    if rating is None:
        return "—"
    full = int(rating)
    half = 1 if rating - full >= 0.5 else 0
    return ("★" * full) + ("½" if half else "")


templates.env.filters["format_stars"] = _format_stars


def _sort_sub_mood_groups(sub_groups: dict[str, list]) -> list[tuple[str, list]]:
    return sorted(
        ((name, films) for name, films in sub_groups.items() if films),
        key=lambda item: (-len(item[1]), item[0].casefold()),
    )


templates.env.filters["sort_sub_moods"] = _sort_sub_mood_groups
app = FastAPI(title="boxdMe")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "default_username": "",
        },
    )


@app.post("/watchlist/sync", response_class=HTMLResponse)
async def sync_watchlist(
    request: Request,
    username: str = Form(...),
    refresh_letterboxd: str = Form("0"),
    refresh_moods: str = Form("0"),
) -> HTMLResponse:
    try:
        result = await _sync_watchlist(
            username,
            refresh_letterboxd=refresh_letterboxd in {"1", "true", "on"},
            refresh_moods=refresh_moods in {"1", "true", "on"},
        )
    except (InvalidUsernameError, WatchlistEmptyError, TmdbError) as error:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"request": request, "message": str(error)},
        )
    except LetterboxdError as error:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"request": request, "message": f"Letterboxd error: {error}"},
        )
    except httpx.HTTPError as error:
        return templates.TemplateResponse(
            request,
            "partials/error.html",
            {"request": request, "message": f"TMDB request failed: {error}"},
        )

    return templates.TemplateResponse(
        request,
        "partials/results.html",
        {
            "request": request,
            "result": result,
        },
    )


def _order_grouped(
    grouped: dict[str, dict[str, list[EnrichedFilm]]],
) -> dict[str, dict[str, list[EnrichedFilm]]]:
    ordered: dict[str, dict[str, list[EnrichedFilm]]] = {}
    for mood in MOOD_ORDER:
        sub_groups = grouped.get(mood)
        if not sub_groups:
            continue
        ordered[mood] = dict(sorted(sub_groups.items(), key=lambda item: item[0].casefold()))
    for mood, sub_groups in grouped.items():
        if mood in ordered:
            continue
        ordered[mood] = dict(sorted(sub_groups.items(), key=lambda item: item[0].casefold()))
    return ordered


def _default_sub_moods(grouped: dict[str, dict[str, list[EnrichedFilm]]]) -> dict[str, str]:
    return {mood: default_sub_mood(sub_groups) for mood, sub_groups in grouped.items()}


def _build_sync_result_from_db(
    username: str,
    *,
    last_synced_at: str,
    used_cached_watchlist: bool = False,
    skipped_tmdb: bool = False,
    refreshed_moods: bool = False,
) -> SyncResult:
    grouped = _order_grouped(get_grouped_films_for_user(username))
    films = [film for sub_groups in grouped.values() for sub_films in sub_groups.values() for film in sub_films]
    unmatched_titles = sorted(
        {film.title for film in films if film.tmdb_id is None},
        key=str.casefold,
    )
    rated_film_count = sum(1 for film in films if film.letterboxd_avg_rating is not None)

    return SyncResult(
        username=username,
        film_count=len(films),
        last_synced_at=last_synced_at,
        mood_order=MOOD_ORDER,
        grouped_films=grouped,
        default_sub_moods=_default_sub_moods(grouped),
        unmatched_titles=unmatched_titles,
        skipped_tv_titles=[],
        used_cached_watchlist=used_cached_watchlist,
        skipped_tmdb=skipped_tmdb,
        refreshed_moods=refreshed_moods,
        rated_film_count=rated_film_count,
    )


async def _ensure_community_ratings(films: list[EnrichedFilm]) -> None:
    if not films:
        return

    slugs = [film.letterboxd_slug for film in films]
    known = get_letterboxd_ratings_for_slugs(slugs)
    for film in films:
        cached_rating = known.get(film.letterboxd_slug)
        if cached_rating is not None:
            film.letterboxd_avg_rating = cached_rating

    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": "boxdMe/0.1 (+https://letterboxd.com)"},
    ) as client:
        fetched = await fetch_missing_average_ratings(
            slugs,
            client=client,
            known={slug: known.get(slug) for slug in slugs},
        )

    if fetched:
        update_letterboxd_avg_ratings(fetched)
        for film in films:
            if film.letterboxd_slug in fetched and fetched[film.letterboxd_slug] is not None:
                film.letterboxd_avg_rating = fetched[film.letterboxd_slug]


def _apply_classification(film: EnrichedFilm) -> None:
    film.mood, film.sub_mood = classify_film(film.genres, film.keywords)


async def _sync_watchlist(
    username: str,
    *,
    refresh_letterboxd: bool = False,
    refresh_moods: bool = False,
) -> SyncResult:
    normalized_username = validate_username(username)

    if refresh_moods:
        if not user_has_cached_watchlist(normalized_username):
            raise WatchlistEmptyError(
                f"No saved watchlist for '{normalized_username}'. Load moods first."
            )
        reclassify_films_for_user(normalized_username)
        films = get_grouped_films_for_user(normalized_username)
        flat = [f for subs in films.values() for sub in subs.values() for f in sub]
        await _ensure_community_ratings(flat)
        last_synced_at = touch_user_last_synced(normalized_username)
        return _build_sync_result_from_db(
            normalized_username,
            last_synced_at=last_synced_at,
            refreshed_moods=True,
        )

    stored_hash = get_user_watchlist_hash(normalized_username)
    if stored_hash is None and user_has_cached_watchlist(normalized_username):
        stored_hash = compute_watchlist_hash_from_slugs(get_user_film_slugs(normalized_username))
        set_user_watchlist_hash(normalized_username, stored_hash)

    if (
        stored_hash
        and user_has_cached_watchlist(normalized_username)
        and not refresh_letterboxd
    ):
        films = get_grouped_films_for_user(normalized_username)
        flat = [f for subs in films.values() for sub in subs.values() for f in sub]
        await _ensure_community_ratings(flat)
        last_synced_at = touch_user_last_synced(normalized_username)
        return _build_sync_result_from_db(
            normalized_username,
            last_synced_at=last_synced_at,
            used_cached_watchlist=True,
        )

    stubs = await fetch_watchlist(normalized_username)
    watchlist_hash = compute_watchlist_hash(stubs)
    if stored_hash and watchlist_hash == stored_hash:
        films = get_grouped_films_for_user(normalized_username)
        flat = [f for subs in films.values() for sub in subs.values() for f in sub]
        await _ensure_community_ratings(flat)
        last_synced_at = touch_user_last_synced(normalized_username)
        return _build_sync_result_from_db(
            normalized_username,
            last_synced_at=last_synced_at,
            skipped_tmdb=True,
        )

    enriched_films: list[EnrichedFilm] = []
    unmatched_titles: list[str] = []
    skipped_tv_titles: list[str] = []
    pending_stubs = []
    cached_films = get_cached_films([stub.letterboxd_slug for stub in stubs])

    for stub in stubs:
        if stub.is_tv:
            skipped_tv_titles.append(stub.title)
            continue

        cached = cached_films.get(stub.letterboxd_slug)
        if cached and cached.tmdb_id is not None and cached.mood:
            cached.title = stub.title
            cached.year = stub.year
            cached.letterboxd_url = stub.letterboxd_url
            _apply_classification(cached)
            enriched_films.append(cached)
            continue
        pending_stubs.append(stub)

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        semaphore = asyncio.Semaphore(4)

        async def enrich_with_limit(stub: FilmStub) -> tuple[EnrichedFilm | None, str]:
            async with semaphore:
                enriched, kind = await enrich_film(stub, client)
                if enriched is not None:
                    _apply_classification(enriched)
                return enriched, kind

        fetched = await asyncio.gather(*(enrich_with_limit(stub) for stub in pending_stubs))

    for stub, (enriched, kind) in zip(pending_stubs, fetched, strict=True):
        if kind == "tv":
            skipped_tv_titles.append(stub.title)
            continue
        if enriched is None:
            continue
        enriched_films.append(enriched)
        if kind == "unmatched":
            unmatched_titles.append(enriched.title)

    enriched_films.sort(key=lambda film: film.title.casefold())
    await _ensure_community_ratings(enriched_films)

    last_synced_at = replace_user_watchlist(
        normalized_username,
        enriched_films,
        watchlist_hash=watchlist_hash,
    )
    grouped = _order_grouped(get_grouped_films_for_user(normalized_username))
    films = [film for sub_groups in grouped.values() for sub_films in sub_groups.values() for film in sub_films]
    rated_film_count = sum(1 for film in films if film.letterboxd_avg_rating is not None)

    return SyncResult(
        username=normalized_username,
        film_count=len(films),
        last_synced_at=last_synced_at,
        mood_order=MOOD_ORDER,
        grouped_films=grouped,
        default_sub_moods=_default_sub_moods(grouped),
        unmatched_titles=unmatched_titles,
        skipped_tv_titles=sorted(set(skipped_tv_titles), key=str.casefold),
        rated_film_count=rated_film_count,
    )
