from __future__ import annotations

import hashlib

from app.models import FilmStub


def compute_watchlist_hash(stubs: list[FilmStub]) -> str:
    return compute_watchlist_hash_from_slugs([stub.letterboxd_slug for stub in stubs])


def compute_watchlist_hash_from_slugs(slugs: list[str]) -> str:
    payload = "\n".join(sorted(slugs))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
