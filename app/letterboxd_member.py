from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from app.letterboxd import LETTERBOXD_BASE_URL, _get_with_retries

MemberFilmData = dict[str, tuple[float | None, str | None]]
LETTERBOXD_NS = "https://letterboxd.com"
FILM_SLUG_PATTERN = re.compile(r"/film/([^/]+)/")


def parse_star_rating(label: str | None) -> float | None:
    if not label:
        return None
    stars = label.count("★")
    half = 0.5 if "½" in label else 0.0
    if stars == 0 and half == 0:
        return None
    return stars + half


def slug_from_film_path(path: str | None) -> str | None:
    if not path:
        return None
    match = FILM_SLUG_PATTERN.search(path)
    return match.group(1) if match else None


def _merge_activity(
    activity: MemberFilmData,
    slug: str,
    rating: float | None,
    review: str | None,
) -> None:
    if not slug:
        return
    existing_rating, existing_review = activity.get(slug, (None, None))
    activity[slug] = (
        rating if rating is not None else existing_rating,
        review if review else existing_review,
    )


async def fetch_member_film_activity(
    username: str,
    *,
    client: httpx.AsyncClient | None = None,
    target_slugs: set[str] | None = None,
    delay_seconds: float = 0.25,
    max_pages: int = 200,
    max_film_page_fetches: int = 2000,
) -> MemberFilmData:
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "boxdMe/0.1 (+https://letterboxd.com)"},
        )

    assert client is not None
    activity: MemberFilmData = {}

    try:
        await _collect_from_films_grid(client, username, activity, delay_seconds, max_pages)
        await _collect_from_diary_rss(client, username, activity)
        if target_slugs:
            await _collect_from_watchlist_grid(
                client,
                username,
                activity,
                delay_seconds,
                max_pages,
            )
        await _collect_from_reviews(client, username, activity, delay_seconds, max_pages)

        if target_slugs:
            missing = {slug for slug in target_slugs if activity.get(slug, (None, None))[0] is None}
            if missing:
                await _collect_from_member_film_pages(
                    client,
                    username,
                    activity,
                    sorted(missing)[:max_film_page_fetches],
                    delay_seconds,
                )
        return activity
    finally:
        if owns_client:
            await client.aclose()


async def _collect_from_films_grid(
    client: httpx.AsyncClient,
    username: str,
    activity: MemberFilmData,
    delay_seconds: float,
    max_pages: int,
) -> None:
    for page_number in range(1, max_pages + 1):
        page_path = f"/{username}/films/" if page_number == 1 else f"/{username}/films/page/{page_number}/"
        response = await _get_with_retries(client, f"{LETTERBOXD_BASE_URL}{page_path}")
        if response.status_code in {403, 404}:
            break
        response.raise_for_status()

        parsed = _parse_films_grid_page(response.text)
        if not parsed:
            break

        for slug, rating in parsed:
            _merge_activity(activity, slug, rating, None)

        await asyncio.sleep(delay_seconds)


async def _collect_from_watchlist_grid(
    client: httpx.AsyncClient,
    username: str,
    activity: MemberFilmData,
    delay_seconds: float,
    max_pages: int,
) -> None:
    for page_number in range(1, max_pages + 1):
        page_path = f"/{username}/watchlist/" if page_number == 1 else f"/{username}/watchlist/page/{page_number}/"
        response = await _get_with_retries(client, f"{LETTERBOXD_BASE_URL}{page_path}")
        if response.status_code in {403, 404}:
            break
        response.raise_for_status()

        parsed = _parse_films_grid_page(response.text)
        if not parsed:
            break

        for slug, rating in parsed:
            _merge_activity(activity, slug, rating, None)

        await asyncio.sleep(delay_seconds)


async def _collect_from_diary_rss(
    client: httpx.AsyncClient,
    username: str,
    activity: MemberFilmData,
) -> None:
    response = await _get_with_retries(client, f"{LETTERBOXD_BASE_URL}/{username}/rss/")
    if response.status_code != 200:
        return

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return

    rating_tag = f"{{{LETTERBOXD_NS}}}memberRating"
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        slug = slug_from_film_path(link)
        if not slug:
            continue

        rating_text = item.findtext(rating_tag)
        rating = float(rating_text) if rating_text else None
        _merge_activity(activity, slug, rating, None)


async def _collect_from_reviews(
    client: httpx.AsyncClient,
    username: str,
    activity: MemberFilmData,
    delay_seconds: float,
    max_pages: int,
) -> None:
    for page_number in range(1, max_pages + 1):
        page_path = f"/{username}/reviews/" if page_number == 1 else f"/{username}/reviews/page/{page_number}/"
        response = await _get_with_retries(client, f"{LETTERBOXD_BASE_URL}{page_path}")
        if response.status_code in {403, 404}:
            return
        response.raise_for_status()

        parsed = _parse_reviews_page(response.text)
        if not parsed:
            break

        for slug, rating, review in parsed:
            _merge_activity(activity, slug, rating, review)

        await asyncio.sleep(delay_seconds)


async def _collect_from_member_film_pages(
    client: httpx.AsyncClient,
    username: str,
    activity: MemberFilmData,
    slugs: list[str],
    delay_seconds: float,
) -> None:
    semaphore = asyncio.Semaphore(4)

    async def fetch_one(slug: str) -> None:
        async with semaphore:
            rating, review = await _fetch_member_film_page(client, username, slug)
            _merge_activity(activity, slug, rating, review)
            await asyncio.sleep(delay_seconds)

    await asyncio.gather(*(fetch_one(slug) for slug in slugs))


async def _fetch_member_film_page(
    client: httpx.AsyncClient,
    username: str,
    slug: str,
) -> tuple[float | None, str | None]:
    response = await _get_with_retries(
        client,
        f"{LETTERBOXD_BASE_URL}/{username}/film/{slug}/",
    )
    if response.status_code != 200:
        return None, None

    soup = BeautifulSoup(response.text, "html.parser")
    rating = _extract_rating(soup)
    review = _extract_review_text(soup)
    return rating, review


def _parse_films_grid_page(html: str) -> list[tuple[str, float | None]]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[tuple[str, float | None]] = []

    for grid_item in soup.select("li.griditem"):
        poster = grid_item.select_one('div.react-component[data-item-link^="/film/"]')
        if poster is None:
            continue
        slug = (poster.get("data-item-slug") or "").strip()
        if not slug:
            continue
        items.append((slug, _extract_rating_from_grid_item(grid_item)))

    return items


def _parse_reviews_page(html: str) -> list[tuple[str, float | None, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[tuple[str, float | None, str | None]] = []

    for article in soup.select("article.production-viewing"):
        poster = article.select_one('div.react-component[data-item-slug][data-item-link^="/film/"]')
        if poster is None:
            continue
        slug = (poster.get("data-item-slug") or "").strip()
        if not slug:
            continue

        rating = _extract_rating(article)
        review = _extract_review_text(article)
        items.append((slug, rating, review))

    return items


def _extract_rating_from_grid_item(grid_item) -> float | None:
    viewing_data = grid_item.select_one("p.poster-viewingdata")
    if viewing_data is not None:
        rating = _extract_rating(viewing_data)
        if rating is not None:
            return rating
        text = viewing_data.get_text(strip=True)
        if "★" in text or "½" in text:
            return parse_star_rating(text)

    rating = _extract_rating(grid_item)
    if rating is not None:
        return rating

    text = grid_item.get_text(strip=True)
    if "★" in text or "½" in text:
        return parse_star_rating(text)
    return None


def _extract_rating(node) -> float | None:
    if node is None:
        return None

    for selector in (
        "span.inline-rating svg[aria-label]",
        "svg.glyph.-rating[aria-label]",
        "svg[aria-label]",
    ):
        rating_node = node.select_one(selector)
        if rating_node is None:
            continue
        rating = parse_star_rating(rating_node.get("aria-label"))
        if rating is not None:
            return rating

    return None


def _extract_review_text(node) -> str | None:
    if node is None:
        return None
    body = node.select_one("div.js-review-body")
    if body is None:
        return None

    paragraphs = [paragraph.get_text(" ", strip=True) for paragraph in body.select("p")]
    text = " ".join(part for part in paragraphs if part).strip()
    return text or None
