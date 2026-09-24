from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# If any of these appear in keywords, do not classify as Cozy Comfort.
COZY_HEAVY_SUBJECT_KEYWORDS: tuple[str, ...] = (
    "abortion",
    "miscarriage",
    "pregnancy",
    "stillbirth",
    "terminal illness",
    "cancer",
    "holocaust",
    "genocide",
    "rape",
    "sexual abuse",
    "suicide",
    "murder",
    "grief",
    "funeral",
    "war crime",
    "torture",
)


MOOD_ORDER = [
    "Dark Tension",
    "Mindbender",
    "Epic Scope",
    "Crime Edge",
    "Romance",
    "Cozy Comfort",
    "Laughs",
    "Feel Good",
    "Arthouse",
    "Uncategorized",
]

MOOD_META: dict[str, dict[str, str]] = {
    "Dark Tension": {
        "excerpt": "Uneasy atmospheres, creeping dread, and stories that keep you glancing over your shoulder.",
        "accent": "mood-accent-dark",
    },
    "Mindbender": {
        "excerpt": "Reality bends, timelines tangle, and the ending might send you back to the start.",
        "accent": "mood-accent-mind",
    },
    "Epic Scope": {
        "excerpt": "Big skies, long journeys, and stakes that reshape kingdoms or history itself.",
        "accent": "mood-accent-epic",
    },
    "Crime Edge": {
        "excerpt": "Heists, grudges, and moral gray zones where everyone has something to hide.",
        "accent": "mood-accent-crime",
    },
    "Romance": {
        "excerpt": "Chemistry, heartbreak, and the messy work of loving someone out loud.",
        "accent": "mood-accent-romance",
    },
    "Cozy Comfort": {
        "excerpt": "Warm light, gentle humor, and films that feel like a blanket on a rainy day.",
        "accent": "mood-accent-cozy",
    },
    "Laughs": {
        "excerpt": "Sharp wit, absurd setups, and the kind of comedy that loosens your shoulders.",
        "accent": "mood-accent-laughs",
    },
    "Feel Good": {
        "excerpt": "Uplifting beats, music in the bones, and endings that leave you lighter.",
        "accent": "mood-accent-feelgood",
    },
    "Arthouse": {
        "excerpt": "Patient frames, odd rhythms, and films that ask you to sit with the silence.",
        "accent": "mood-accent-art",
    },
    "Uncategorized": {
        "excerpt": "Watchlist gems that did not land in a clear bucket yet — still worth a look.",
        "accent": "mood-accent-neutral",
    },
}


def mood_slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def mood_meta(name: str) -> dict[str, str]:
    return MOOD_META.get(name, MOOD_META["Uncategorized"])


def default_sub_mood(sub_groups: dict[str, list]) -> str:
    non_general = [(name, len(films)) for name, films in sub_groups.items() if name != "General" and films]
    if non_general:
        return min(non_general, key=lambda item: item[1])[0]
    with_films = [(name, len(films)) for name, films in sub_groups.items() if films]
    if with_films:
        return max(with_films, key=lambda item: item[1])[0]
    return "General"


@dataclass(frozen=True, slots=True)
class MoodRule:
    name: str
    genres_any: frozenset[str] = frozenset()
    keywords_any: tuple[str, ...] = ()
    genres_all: frozenset[str] = frozenset()
    keywords_block: tuple[str, ...] = ()
    match: Literal["any", "all"] = "any"


RULES = [
    MoodRule(
        name="Dark Tension",
        genres_any=frozenset({"Horror", "Thriller", "Mystery"}),
        keywords_any=(
            "psychological",
            "serial killer",
            "haunted",
            "supernatural",
            "slasher",
            "survival horror",
        ),
    ),
    MoodRule(
        name="Mindbender",
        genres_any=frozenset({"Science Fiction", "Fantasy"}),
        keywords_any=("time travel", "dystopia", "parallel world", "dream", "simulation"),
    ),
    MoodRule(
        name="Epic Scope",
        genres_any=frozenset({"War", "History", "Adventure", "Western"}),
        keywords_any=("epic", "quest", "kingdom", "battle", "empire", "based on true story"),
    ),
    MoodRule(
        name="Crime Edge",
        genres_any=frozenset({"Crime"}),
        keywords_any=("heist", "gangster", "detective", "film noir", "mob", "police"),
    ),
    MoodRule(
        name="Romance",
        genres_any=frozenset({"Romance"}),
        keywords_any=("love story", "relationship", "breakup", "courtship"),
    ),
    MoodRule(
        name="Arthouse",
        genres_any=frozenset({"Drama", "Documentary"}),
        keywords_any=("art house", "slow cinema", "experimental", "meditative", "festival"),
    ),
    MoodRule(
        name="Cozy Comfort",
        genres_any=frozenset({"Family", "Animation"}),
        keywords_any=("christmas", "holiday", "feel good"),
        keywords_block=COZY_HEAVY_SUBJECT_KEYWORDS,
    ),
    MoodRule(
        name="Laughs",
        genres_any=frozenset({"Comedy"}),
        keywords_any=("satire", "spoof", "workplace comedy", "buddy comedy", "romantic comedy"),
    ),
    MoodRule(
        name="Feel Good",
        genres_any=frozenset({"Music", "TV Movie"}),
        keywords_any=("sports", "dance", "musician", "inspirational", "uplifting"),
    ),
]

SUB_MOOD_RULES: dict[str, tuple[MoodRule, ...]] = {
    "Dark Tension": (
        MoodRule(name="Supernatural", keywords_any=("supernatural", "haunted", "ghost", "demon", "paranormal", "witch")),
        MoodRule(name="Slasher", keywords_any=("slasher", "survival horror", "masked killer")),
        MoodRule(name="Psychological", keywords_any=("psychological", "mind game", "unreliable narrator")),
        MoodRule(name="Serial killer", keywords_any=("serial killer", "murder investigation")),
        MoodRule(name="Horror", genres_any=frozenset({"Horror"})),
        MoodRule(name="Thriller", genres_any=frozenset({"Thriller"})),
        MoodRule(name="Mystery", genres_any=frozenset({"Mystery"})),
    ),
    "Mindbender": (
        MoodRule(name="Time travel", keywords_any=("time travel", "time loop", "timeline")),
        MoodRule(name="Dystopia", keywords_any=("dystopia", "dystopian", "post-apocalyptic")),
        MoodRule(name="Dream logic", keywords_any=("dream", "simulation", "virtual reality", "parallel world")),
        MoodRule(name="Sci-Fi", genres_any=frozenset({"Science Fiction"})),
        MoodRule(name="Fantasy", genres_any=frozenset({"Fantasy"})),
    ),
    "Epic Scope": (
        MoodRule(name="War", genres_any=frozenset({"War"})),
        MoodRule(name="History", genres_any=frozenset({"History"})),
        MoodRule(name="Adventure", genres_any=frozenset({"Adventure"})),
        MoodRule(name="Western", genres_any=frozenset({"Western"})),
        MoodRule(name="Quest", keywords_any=("quest", "journey", "expedition", "epic")),
    ),
    "Crime Edge": (
        MoodRule(name="Heist", keywords_any=("heist", "robbery", "vault")),
        MoodRule(name="Gangster", keywords_any=("gangster", "mob", "mafia", "organized crime")),
        MoodRule(name="Noir", keywords_any=("film noir", "neo-noir", "detective")),
        MoodRule(name="Police", keywords_any=("police", "cop", "investigation", "detective")),
    ),
    "Romance": (
        MoodRule(name="Rom-com", keywords_any=("romantic comedy", "rom-com")),
        MoodRule(name="Heartbreak", keywords_any=("breakup", "heartbreak", "affair")),
        MoodRule(name="Love story", keywords_any=("love story", "courtship", "relationship")),
    ),
    "Cozy Comfort": (
        MoodRule(name="Holiday", keywords_any=("christmas", "holiday", "thanksgiving")),
        MoodRule(
            name="Coming of age",
            genres_any=frozenset({"Family", "Animation"}),
            keywords_any=("coming of age", "childhood", "teenager"),
            match="all",
        ),
        MoodRule(name="Animation", genres_any=frozenset({"Animation"})),
        MoodRule(name="Family", genres_any=frozenset({"Family"})),
    ),
    "Laughs": (
        MoodRule(name="Satire", keywords_any=("satire", "spoof", "parody")),
        MoodRule(name="Rom-com", keywords_any=("romantic comedy", "rom-com")),
        MoodRule(name="Buddy comedy", keywords_any=("buddy comedy", "buddy film")),
        MoodRule(name="Workplace", keywords_any=("workplace comedy", "office")),
    ),
    "Feel Good": (
        MoodRule(name="Music", genres_any=frozenset({"Music"})),
        MoodRule(name="Sports", keywords_any=("sports", "athlete", "championship", "team")),
        MoodRule(name="Inspirational", keywords_any=("inspirational", "uplifting", "underdog")),
    ),
    "Arthouse": (
        MoodRule(name="Documentary", genres_any=frozenset({"Documentary"})),
        MoodRule(name="Experimental", keywords_any=("experimental", "art house", "avant-garde", "surreal")),
        MoodRule(name="Slow cinema", keywords_any=("slow cinema", "meditative", "minimalist")),
        MoodRule(name="Drama", genres_any=frozenset({"Drama"})),
    ),
}


def _match_rule(rule: MoodRule, genre_set: set[str], keyword_blob: str) -> bool:
    if rule.keywords_block and any(term in keyword_blob for term in rule.keywords_block):
        return False
    if rule.genres_all and not rule.genres_all.issubset(genre_set):
        return False

    genre_hit = bool(rule.genres_any and genre_set.intersection(rule.genres_any))
    keyword_hit = bool(rule.keywords_any and any(term in keyword_blob for term in rule.keywords_any))

    if rule.match == "all":
        if rule.genres_any and rule.keywords_any:
            return genre_hit and keyword_hit
        if rule.genres_any:
            return genre_hit
        if rule.keywords_any:
            return keyword_hit
        return False

    if genre_hit or keyword_hit:
        return True
    return False


def classify_mood(genres: list[str], keywords: list[str]) -> str:
    genre_set = {genre.strip() for genre in genres if genre.strip()}
    keyword_blob = " | ".join(keyword.lower() for keyword in keywords)

    for rule in RULES:
        if _match_rule(rule, genre_set, keyword_blob):
            return rule.name

    return "Uncategorized"


def classify_sub_mood(parent: str, genres: list[str], keywords: list[str]) -> str:
    rules = SUB_MOOD_RULES.get(parent)
    if not rules:
        return "General"

    genre_set = {genre.strip() for genre in genres if genre.strip()}
    keyword_blob = " | ".join(keyword.lower() for keyword in keywords)

    for rule in rules:
        if _match_rule(rule, genre_set, keyword_blob):
            return rule.name

    return "General"


def classify_film(genres: list[str], keywords: list[str]) -> tuple[str, str]:
    parent = classify_mood(genres, keywords)
    sub = classify_sub_mood(parent, genres, keywords)
    return parent, sub
