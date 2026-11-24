from __future__ import annotations

import asyncio
import json
import re

import httpx

from app.letterboxd import LETTERBOXD_BASE_URL, LetterboxdError, _get_with_retries

CDATA_JSON_PATTERN = re.compile(r"CDATA\[(\{.*\})\]", re.DOTALL)
TMDB_MOVIE_HREF_PATTERN = re.compile(
    r"https?://(?:www\.)?themoviedb\.org/movie/(\d+)",
    re.IGNORECASE,
)
TMDB_TRACK_LINK_PATTERN = re.compile(
    r'<a[^>]+data-track-action=["\']TMDB["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
TMDB_TRACK_LINK_PATTERN_ALT = re.compile(
    r'<a[^>]+href=["\']([^"\']*themoviedb\.org/movie/\d+[^"\']*)["\'][^>]+data-track-action=["\']TMDB["\']',
    re.IGNORECASE,
)


async def _fetch_film_page_html(slug: str, client: httpx.AsyncClient) -> str | None:
    url = f"{LETTERBOXD_BASE_URL}/film/{slug}/"
    try:
        response = await _get_with_retries(client, url)
    except (LetterboxdError, httpx.HTTPError):
        return None

    if response.status_code != 200:
        return None

    return response.text


def parse_tmdb_id_from_film_html(html: str) -> int | None:
    for pattern in (TMDB_TRACK_LINK_PATTERN, TMDB_TRACK_LINK_PATTERN_ALT):
        match = pattern.search(html)
        if match:
            href_match = TMDB_MOVIE_HREF_PATTERN.search(match.group(1))
            if href_match:
                return int(href_match.group(1))

    fallback = TMDB_MOVIE_HREF_PATTERN.search(html)
    if fallback:
        return int(fallback.group(1))

    return None


async def fetch_letterboxd_tmdb_id(slug: str, client: httpx.AsyncClient) -> int | None:
    html = await _fetch_film_page_html(slug, client)
    if html is None:
        return None
    return parse_tmdb_id_from_film_html(html)


async def fetch_film_average_rating(
    slug: str,
    client: httpx.AsyncClient,
) -> float | None:
    html = await _fetch_film_page_html(slug, client)
    if html is None:
        return None
    return _parse_average_rating(html)


def _parse_average_rating(html: str) -> float | None:
    rating = _rating_from_json_ld(html)
    if rating is not None:
        return rating
    return _rating_from_twitter_meta(html)


def _rating_from_json_ld(html: str) -> float | None:
    for match in CDATA_JSON_PATTERN.finditer(html):
        raw = match.group(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        aggregate = data.get("aggregateRating")
        if not isinstance(aggregate, dict):
            continue
        value = aggregate.get("ratingValue")
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if 0 <= parsed <= 5:
            return parsed

    return None


def _rating_from_twitter_meta(html: str) -> float | None:
    match = re.search(
        r'<meta\s+name="twitter:data2"\s+content="([0-9.]+)\s+out of\s+5"',
        html,
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        parsed = float(match.group(1))
    except ValueError:
        return None
    if 0 <= parsed <= 5:
        return parsed
    return None


async def fetch_missing_average_ratings(
    slugs: list[str],
    *,
    client: httpx.AsyncClient,
    known: dict[str, float | None],
    semaphore_limit: int = 4,
) -> dict[str, float | None]:
    to_fetch = [slug for slug in slugs if known.get(slug) is None]
    if not to_fetch:
        return {}

    semaphore = asyncio.Semaphore(semaphore_limit)
    results: dict[str, float | None] = {}

    async def fetch_one(slug: str) -> None:
        async with semaphore:
            results[slug] = await fetch_film_average_rating(slug, client)
            await asyncio.sleep(0.15)

    await asyncio.gather(*(fetch_one(slug) for slug in to_fetch))
    return results
