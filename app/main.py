from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    get_persist_username,
    get_retention_hours,
    is_persisted_user,
    local_cache_note,
    session_cache_note,
)
from app import ephemeral_store
from app.db import (
    get_cached_films,
    get_grouped_films_for_user,
    get_letterboxd_ratings_for_slugs,
    get_user_film_slugs,
    get_user_watchlist_hash,
    init_db,
    purge_stale_watchlists,
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
from app.mood_explorer_css import build_mood_explorer_css
from app.tmdb import TmdbError, enrich_film
from app.watchlist_hash import compute_watchlist_hash, compute_watchlist_hash_from_slugs

load_dotenv()

logger = logging.getLogger("boxdme")

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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run_retention_purge() -> None:
    hours = get_retention_hours()
    users_deleted, films_deleted = purge_stale_watchlists(retention_hours=hours)
    evicted = ephemeral_store.purge_inactive(retention_hours=hours)
    if users_deleted or films_deleted or evicted:
        logger.info(
            "Retention purge: users=%s orphan_films=%s ephemeral=%s",
            users_deleted,
            films_deleted,
            evicted,
        )


async def _retention_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        _run_retention_purge()


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    _run_retention_purge()
    asyncio.create_task(_retention_loop())


def _index_storage_hint() -> str:
    owner = get_persist_username()
    hours = get_retention_hours()
    if owner:
        return (
            f"Only @{owner} is saved on this server's disk (removed after {hours} hours "
            f"without use). Other usernames are processed in memory only."
        )
    return (
        f"Watchlists are not saved to disk — session memory only, cleared after "
        f"{hours} hours without use."
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "default_username": "",
            "persist_username": get_persist_username(),
            "retention_hours": get_retention_hours(),
            "storage_hint": _index_storage_hint(),
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
            "mood_explorer_css": build_mood_explorer_css(result.grouped_films),
        },
    )


def _mood_film_count(sub_groups: dict[str, list[EnrichedFilm]]) -> int:
    return sum(len(films) for films in sub_groups.values())


def _order_grouped(
    grouped: dict[str, dict[str, list[EnrichedFilm]]],
) -> dict[str, dict[str, list[EnrichedFilm]]]:
    mood_rank = {mood: index for index, mood in enumerate(MOOD_ORDER)}
    fallback_rank = len(MOOD_ORDER)

    def mood_sort_key(mood: str) -> tuple[int, int, str]:
        count = _mood_film_count(grouped[mood])
        return (-count, mood_rank.get(mood, fallback_rank), mood.casefold())

    ordered: dict[str, dict[str, list[EnrichedFilm]]] = {}
    for mood in sorted(grouped, key=mood_sort_key):
        sub_groups = grouped[mood]
        ordered[mood] = dict(sorted(sub_groups.items(), key=lambda item: item[0].casefold()))
    return ordered


def _group_enriched_films(films: list[EnrichedFilm]) -> dict[str, dict[str, list[EnrichedFilm]]]:
    grouped: dict[str, dict[str, list[EnrichedFilm]]] = {}
    for film in films:
        grouped.setdefault(film.mood, {}).setdefault(film.sub_mood, []).append(film)
    return _order_grouped(grouped)


def _default_sub_moods(grouped: dict[str, dict[str, list[EnrichedFilm]]]) -> dict[str, str]:
    return {mood: default_sub_mood(sub_groups) for mood, sub_groups in grouped.items()}


def _build_sync_result(
    username: str,
    grouped: dict[str, dict[str, list[EnrichedFilm]]],
    *,
    last_synced_at: str,
    storage_mode: Literal["local", "session"],
    retention_hours: int,
    cache_note: str,
    unmatched_titles: list[str] | None = None,
    skipped_tv_titles: list[str] | None = None,
    used_cached_watchlist: bool = False,
    skipped_tmdb: bool = False,
    refreshed_moods: bool = False,
) -> SyncResult:
    films = [film for sub_groups in grouped.values() for sub_films in sub_groups.values() for film in sub_films]
    unmatched = unmatched_titles if unmatched_titles is not None else sorted(
        {film.title for film in films if film.tmdb_id is None},
        key=str.casefold,
    )
    rated_film_count = sum(1 for film in films if film.letterboxd_avg_rating is not None)

    return SyncResult(
        username=username,
        film_count=len(films),
        last_synced_at=last_synced_at,
        mood_order=list(grouped.keys()),
        grouped_films=grouped,
        default_sub_moods=_default_sub_moods(grouped),
        unmatched_titles=unmatched,
        skipped_tv_titles=skipped_tv_titles or [],
        used_cached_watchlist=used_cached_watchlist,
        skipped_tmdb=skipped_tmdb,
        refreshed_moods=refreshed_moods,
        rated_film_count=rated_film_count,
        storage_mode=storage_mode,
        retention_hours=retention_hours,
        cache_note=cache_note,
    )


def _build_sync_result_from_db(
    username: str,
    *,
    last_synced_at: str,
    used_cached_watchlist: bool = False,
    skipped_tmdb: bool = False,
    refreshed_moods: bool = False,
) -> SyncResult:
    hours = get_retention_hours()
    grouped = _order_grouped(get_grouped_films_for_user(username))
    return _build_sync_result(
        username,
        grouped,
        last_synced_at=last_synced_at,
        storage_mode="local",
        retention_hours=hours,
        cache_note=local_cache_note(hours),
        used_cached_watchlist=used_cached_watchlist,
        skipped_tmdb=skipped_tmdb,
        refreshed_moods=refreshed_moods,
    )


def _build_sync_result_from_films(
    username: str,
    enriched_films: list[EnrichedFilm],
    *,
    last_synced_at: str,
    unmatched_titles: list[str] | None = None,
    skipped_tv_titles: list[str] | None = None,
    used_cached_watchlist: bool = False,
    skipped_tmdb: bool = False,
    refreshed_moods: bool = False,
) -> SyncResult:
    hours = get_retention_hours()
    grouped = _group_enriched_films(enriched_films)
    return _build_sync_result(
        username,
        grouped,
        last_synced_at=last_synced_at,
        storage_mode="session",
        retention_hours=hours,
        cache_note=session_cache_note(hours),
        unmatched_titles=unmatched_titles,
        skipped_tv_titles=skipped_tv_titles,
        used_cached_watchlist=used_cached_watchlist,
        skipped_tmdb=skipped_tmdb,
        refreshed_moods=refreshed_moods,
    )


async def _ensure_community_ratings_persisted(films: list[EnrichedFilm]) -> None:
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


async def _ensure_community_ratings_session(films: list[EnrichedFilm]) -> None:
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

    for film in films:
        rating = fetched.get(film.letterboxd_slug)
        if rating is not None:
            film.letterboxd_avg_rating = rating


def _apply_classification(film: EnrichedFilm) -> None:
    film.mood, film.sub_mood = classify_film(film.genres, film.keywords)


async def _enrich_stubs(
    stubs: list[FilmStub],
    *,
    read_cached_films: bool,
) -> tuple[list[EnrichedFilm], list[str], list[str]]:
    enriched_films: list[EnrichedFilm] = []
    unmatched_titles: list[str] = []
    skipped_tv_titles: list[str] = []
    pending_stubs: list[FilmStub] = []
    cached_films = get_cached_films([stub.letterboxd_slug for stub in stubs]) if read_cached_films else {}

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
    return enriched_films, unmatched_titles, skipped_tv_titles


async def _sync_watchlist(
    username: str,
    *,
    refresh_letterboxd: bool = False,
    refresh_moods: bool = False,
) -> SyncResult:
    normalized_username = validate_username(username)
    if is_persisted_user(normalized_username):
        return await _sync_watchlist_persisted(
            normalized_username,
            refresh_letterboxd=refresh_letterboxd,
            refresh_moods=refresh_moods,
        )
    return await _sync_watchlist_ephemeral(
        normalized_username,
        refresh_letterboxd=refresh_letterboxd,
        refresh_moods=refresh_moods,
    )


async def _sync_watchlist_persisted(
    normalized_username: str,
    *,
    refresh_letterboxd: bool,
    refresh_moods: bool,
) -> SyncResult:
    if refresh_moods:
        if not user_has_cached_watchlist(normalized_username):
            raise WatchlistEmptyError(
                f"No saved watchlist for '{normalized_username}'. Load moods first."
            )
        reclassify_films_for_user(normalized_username)
        films = get_grouped_films_for_user(normalized_username)
        flat = [f for subs in films.values() for sub in subs.values() for f in sub]
        await _ensure_community_ratings_persisted(flat)
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
        await _ensure_community_ratings_persisted(flat)
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
        await _ensure_community_ratings_persisted(flat)
        last_synced_at = touch_user_last_synced(normalized_username)
        return _build_sync_result_from_db(
            normalized_username,
            last_synced_at=last_synced_at,
            skipped_tmdb=True,
        )

    enriched_films, unmatched_titles, skipped_tv_titles = await _enrich_stubs(
        stubs,
        read_cached_films=True,
    )
    await _ensure_community_ratings_persisted(enriched_films)

    last_synced_at = replace_user_watchlist(
        normalized_username,
        enriched_films,
        watchlist_hash=watchlist_hash,
    )
    grouped = _order_grouped(get_grouped_films_for_user(normalized_username))
    hours = get_retention_hours()
    return _build_sync_result(
        normalized_username,
        grouped,
        last_synced_at=last_synced_at,
        storage_mode="local",
        retention_hours=hours,
        cache_note=local_cache_note(hours),
        unmatched_titles=unmatched_titles,
        skipped_tv_titles=sorted(set(skipped_tv_titles), key=str.casefold),
    )


async def _sync_watchlist_ephemeral(
    normalized_username: str,
    *,
    refresh_letterboxd: bool,
    refresh_moods: bool,
) -> SyncResult:
    entry = ephemeral_store.get(normalized_username)

    if refresh_moods:
        if entry is None or not entry.enriched_films:
            raise WatchlistEmptyError(
                f"No saved watchlist for '{normalized_username}'. Load moods first."
            )
        for film in entry.enriched_films:
            _apply_classification(film)
        await _ensure_community_ratings_session(entry.enriched_films)
        entry.last_synced_at = _now_iso()
        entry.touch()
        return _build_sync_result_from_films(
            normalized_username,
            entry.enriched_films,
            last_synced_at=entry.last_synced_at,
            refreshed_moods=True,
        )

    stored_hash = entry.watchlist_hash if entry else None

    if entry and stored_hash and not refresh_letterboxd:
        await _ensure_community_ratings_session(entry.enriched_films)
        entry.last_synced_at = _now_iso()
        entry.touch()
        return _build_sync_result_from_films(
            normalized_username,
            entry.enriched_films,
            last_synced_at=entry.last_synced_at,
            used_cached_watchlist=True,
        )

    stubs = await fetch_watchlist(normalized_username)
    watchlist_hash = compute_watchlist_hash(stubs)

    if entry and stored_hash and watchlist_hash == stored_hash:
        await _ensure_community_ratings_session(entry.enriched_films)
        entry.last_synced_at = _now_iso()
        entry.touch()
        return _build_sync_result_from_films(
            normalized_username,
            entry.enriched_films,
            last_synced_at=entry.last_synced_at,
            skipped_tmdb=True,
        )

    enriched_films, unmatched_titles, skipped_tv_titles = await _enrich_stubs(
        stubs,
        read_cached_films=True,
    )
    await _ensure_community_ratings_session(enriched_films)

    last_synced_at = _now_iso()
    ephemeral_store.put(
        normalized_username,
        watchlist_hash=watchlist_hash,
        enriched_films=enriched_films,
        last_synced_at=last_synced_at,
    )

    return _build_sync_result_from_films(
        normalized_username,
        enriched_films,
        last_synced_at=last_synced_at,
        unmatched_titles=unmatched_titles,
        skipped_tv_titles=sorted(set(skipped_tv_titles), key=str.casefold),
    )
