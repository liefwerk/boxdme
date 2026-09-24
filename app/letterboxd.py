from __future__ import annotations

import asyncio
import re

import httpx
from bs4 import BeautifulSoup

from app.models import FilmStub

LETTERBOXD_BASE_URL = "https://letterboxd.com"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,15}$")
TITLE_YEAR_PATTERN = re.compile(r"^(?P<title>.+?) \((?P<year>\d{4})\)$")


class LetterboxdError(Exception):
    pass


class InvalidUsernameError(LetterboxdError):
    pass


class WatchlistEmptyError(LetterboxdError):
    pass


def validate_username(username: str) -> str:
    cleaned = username.strip()
    if not USERNAME_PATTERN.fullmatch(cleaned):
        raise InvalidUsernameError("Usernames must be 2-15 characters using letters, numbers, underscores, or hyphens.")
    return cleaned


async def fetch_watchlist(
    username: str,
    *,
    client: httpx.AsyncClient | None = None,
    delay_seconds: float = 0.3,
    max_pages: int = 250,
) -> list[FilmStub]:
    username = validate_username(username)
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "boxdMe/0.1 (+https://letterboxd.com)"},
        )

    assert client is not None
    try:
        films: list[FilmStub] = []
        seen_slugs: set[str] = set()

        for page_number in range(1, max_pages + 1):
            page_films = await _fetch_watchlist_page(client, username, page_number)
            if not page_films:
                break

            for film in page_films:
                if film.letterboxd_slug in seen_slugs:
                    continue
                seen_slugs.add(film.letterboxd_slug)
                films.append(film)

            await asyncio.sleep(delay_seconds)

        if not films:
            raise WatchlistEmptyError(f"No public watchlist films found for '{username}'.")

        return films
    finally:
        if owns_client:
            await client.aclose()


async def _fetch_watchlist_page(client: httpx.AsyncClient, username: str, page_number: int) -> list[FilmStub]:
    page_path = f"/{username}/watchlist/" if page_number == 1 else f"/{username}/watchlist/page/{page_number}/"
    url = f"{LETTERBOXD_BASE_URL}{page_path}"

    response = await _get_with_retries(client, url)
    if response.status_code == 404 and page_number == 1:
        raise InvalidUsernameError(f"Could not find a public watchlist for '{username}'.")
    if response.status_code == 404:
        return []
    response.raise_for_status()

    return _parse_watchlist_page(response.text)


async def _get_with_retries(client: httpx.AsyncClient, url: str, retries: int = 2) -> httpx.Response:
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            response = await client.get(url)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            return response
        except httpx.HTTPError as error:
            last_error = error
            if attempt < retries:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
            raise LetterboxdError("Letterboxd request failed.") from error

    raise LetterboxdError("Letterboxd request failed.") from last_error


def _parse_watchlist_page(html: str) -> list[FilmStub]:
    soup = BeautifulSoup(html, "html.parser")
    poster_nodes = soup.select(
        'div.react-component[data-item-link^="/film/"], div.react-component[data-item-link^="/tv/"]'
    )
    films: list[FilmStub] = []

    for node in poster_nodes:
        slug = (node.get("data-item-slug") or "").strip()
        link = (node.get("data-item-link") or "").strip()
        item_name = (node.get("data-item-name") or "").strip()
        if not slug or not link or not item_name:
            continue

        match = TITLE_YEAR_PATTERN.match(item_name)
        if match:
            title = match.group("title").strip()
            year = int(match.group("year"))
        else:
            title = item_name
            year = None

        films.append(
            FilmStub(
                letterboxd_slug=slug,
                title=title,
                year=year,
                letterboxd_url=f"{LETTERBOXD_BASE_URL}{link}",
                is_tv=link.startswith("/tv/"),
            )
        )

    return films
