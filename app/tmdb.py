from __future__ import annotations

import os
import re
from asyncio import sleep

import httpx

from typing import Literal

from app.letterboxd_film import fetch_letterboxd_tmdb_id
from app.models import EnrichedFilm, FilmStub

EnrichKind = Literal["movie", "tv", "unmatched"]

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w342"

_TITLE_NORMALIZE = re.compile(r"[^a-z0-9]+")


class TmdbError(Exception):
    pass


def get_api_key() -> str:
    api_key = os.getenv("TMDB_API_KEY", "").strip()
    if not api_key:
        raise TmdbError("TMDB_API_KEY is missing. Add it to your .env file before syncing.")
    return api_key


def normalize_title(title: str) -> str:
    collapsed = _TITLE_NORMALIZE.sub(" ", title.casefold()).strip()
    return collapsed


def _movie_titles_match(stub_title: str, result: dict) -> bool:
    normalized_stub = normalize_title(stub_title)
    if not normalized_stub:
        return False

    candidate_titles = [
        result.get("title") or "",
        result.get("original_title") or "",
    ]
    for candidate in candidate_titles:
        normalized_candidate = normalize_title(candidate)
        if not normalized_candidate:
            continue
        if normalized_stub == normalized_candidate:
            return True
        if normalized_stub in normalized_candidate or normalized_candidate in normalized_stub:
            return True

    stub_tokens = set(normalized_stub.split())
    if len(stub_tokens) < 2:
        return False

    for candidate in candidate_titles:
        candidate_tokens = set(normalize_title(candidate).split())
        if not candidate_tokens:
            continue
        overlap = len(stub_tokens & candidate_tokens) / len(stub_tokens)
        if overlap >= 0.85:
            return True

    return False


async def enrich_film(stub: FilmStub, client: httpx.AsyncClient) -> tuple[EnrichedFilm | None, EnrichKind]:
    if stub.is_tv:
        return None, "tv"

    api_key = get_api_key()
    letterboxd_tmdb_id = await fetch_letterboxd_tmdb_id(stub.letterboxd_slug, client)
    if letterboxd_tmdb_id is not None:
        details = await _get_movie_details(client, letterboxd_tmdb_id, api_key)
        if details is not None:
            return _enriched_from_details(stub, details), "movie"

    search_params: dict[str, str] = {
        "api_key": api_key,
        "query": stub.title,
    }
    if stub.year:
        search_params["year"] = str(stub.year)

    search_payload = await _get_json_with_retries(client, f"{TMDB_BASE_URL}/search/movie", params=search_params)
    search_results = search_payload.get("results", [])
    match = _pick_best_match(search_results, stub.title, stub.year)

    if not match:
        if await _is_tv_show(stub, client, api_key):
            return None, "tv"
        return (
            EnrichedFilm(
                letterboxd_slug=stub.letterboxd_slug,
                title=stub.title,
                year=stub.year,
                letterboxd_url=stub.letterboxd_url,
            ),
            "unmatched",
        )

    details = await _get_movie_details(client, int(match["id"]), api_key)
    if details is None:
        return (
            EnrichedFilm(
                letterboxd_slug=stub.letterboxd_slug,
                title=stub.title,
                year=stub.year,
                letterboxd_url=stub.letterboxd_url,
            ),
            "unmatched",
        )

    return _enriched_from_details(stub, details), "movie"


async def _get_movie_details(client: httpx.AsyncClient, tmdb_id: int, api_key: str) -> dict | None:
    try:
        return await _get_json_with_retries(
            client,
            f"{TMDB_BASE_URL}/movie/{tmdb_id}",
            params={"api_key": api_key, "append_to_response": "keywords"},
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            return None
        raise


def _enriched_from_details(stub: FilmStub, details: dict) -> EnrichedFilm:
    keywords_payload = details.get("keywords", {})
    keywords = keywords_payload.get("keywords") or keywords_payload.get("results") or []
    poster_path = details.get("poster_path")

    return EnrichedFilm(
        letterboxd_slug=stub.letterboxd_slug,
        title=stub.title,
        year=stub.year,
        letterboxd_url=stub.letterboxd_url,
        tmdb_id=details["id"],
        poster_url=f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None,
        genres=[genre["name"] for genre in details.get("genres", []) if genre.get("name")],
        keywords=[keyword["name"] for keyword in keywords if keyword.get("name")],
    )


async def _is_tv_show(stub: FilmStub, client: httpx.AsyncClient, api_key: str) -> bool:
    params: dict[str, str] = {"api_key": api_key, "query": stub.title}
    if stub.year:
        params["first_air_date_year"] = str(stub.year)

    payload = await _get_json_with_retries(client, f"{TMDB_BASE_URL}/search/tv", params=params)
    return _pick_best_tv_match(payload.get("results", []), stub.title, stub.year) is not None


def _pick_best_tv_match(results: list[dict], title: str, year: int | None) -> dict | None:
    if not results:
        return None

    normalized_title = normalize_title(title)
    title_matches = [result for result in results if normalize_title(result.get("name") or "") == normalized_title]
    candidates = title_matches or results

    if year is not None:
        exact_year = [
            result
            for result in candidates
            if str(year) == str((result.get("first_air_date") or "")[:4])
        ]
        if exact_year:
            return exact_year[0]

    if title_matches:
        return title_matches[0]

    return None


def _pick_best_match(results: list[dict], title: str, year: int | None) -> dict | None:
    if not results:
        return None

    title_aligned = [result for result in results if _movie_titles_match(title, result)]
    if not title_aligned:
        return None

    if year is not None:
        exact_year = [
            result
            for result in title_aligned
            if str(year) == str((result.get("release_date") or "")[:4])
        ]
        if exact_year:
            return exact_year[0]
        return None

    return title_aligned[0]


async def _get_json_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str],
    retries: int = 3,
) -> dict:
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            response = await client.get(url, params=params)
            if response.status_code == 429 and attempt < retries:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after and retry_after.isdigit() else 1.0 + attempt
                await sleep(wait_seconds)
                continue

            if response.status_code in {500, 502, 503, 504} and attempt < retries:
                await sleep(0.8 * (attempt + 1))
                continue

            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as error:
            last_error = error
            if attempt < retries:
                await sleep(0.8 * (attempt + 1))
                continue
            raise

    raise TmdbError("TMDB request failed.") from last_error
