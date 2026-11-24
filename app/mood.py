from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Tone = Literal["heavy", "neutral", "light"]

GENRE_SCORE = 3
KEYWORD_SCORE = 2
PENALTY_SCORE = 4
MIN_MOOD_SCORE = 1

# TMDB keyword substring block for Cozy & Warm (see keywords_block on that mood).
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
    "cruel",
    "cruelty",
    "violence",
    "violent",
    "disturbing",
    "tragic",
    "tragedy",
    "trauma",
    "abuse",
    "bullying",
    "dark",
    "bleak",
    "dystopia",
    "dystopian",
)

HEAVY_TONE_EXTRA_KEYWORDS: tuple[str, ...] = (
    "horror",
    "slasher",
    "serial killer",
    "psychological",
    "neo-noir",
    "film noir",
    "noir",
    "suspense",
    "terror",
    "nightmare",
    "revenge",
    "hostage",
    "kidnapping",
    "dark comedy",
    "survival horror",
)

HEAVY_TONE_KEYWORDS: tuple[str, ...] = COZY_HEAVY_SUBJECT_KEYWORDS + HEAVY_TONE_EXTRA_KEYWORDS

HEAVY_TONE_GENRES: frozenset[str] = frozenset({"Horror", "Thriller", "Mystery"})

LIGHT_TONE_KEYWORDS: tuple[str, ...] = (
    "feel good",
    "heartwarming",
    "uplifting",
    "inspirational",
    "buddy comedy",
    "satire",
    "spoof",
    "parody",
    "romantic comedy",
    "rom-com",
    "holiday",
    "christmas",
    "whimsical",
    "cheerful",
    "funny",
    "slapstick",
    "feel-good",
)

# Parent moods that need a lighter overall tone (see classify_tone).
MOOD_TONE_ALLOW: dict[str, frozenset[Tone]] = {
    "Laughs": frozenset({"light", "neutral"}),
    "Cozy & Warm": frozenset({"light", "neutral"}),
}

MOOD_KEYWORD_PENALTIES: dict[str, tuple[str, ...]] = {
    "Laughs": (
        "horror",
        "slasher",
        "serial killer",
        "psychological",
        "neo-noir",
        "film noir",
        "dark comedy",
        "tragedy",
        "murder",
        "disturbing",
        "supernatural",
        "haunted",
        "revenge",
        "noir",
        "survival horror",
    ),
}


@dataclass(frozen=True, slots=True)
class MatchCriteria:
    genres_any: frozenset[str] = frozenset()
    keywords_any: tuple[str, ...] = ()
    genres_all: frozenset[str] = frozenset()
    keywords_block: tuple[str, ...] = ()
    match: Literal["any", "all"] = "any"


@dataclass(frozen=True, slots=True)
class SubMoodDef:
    name: str
    criteria: MatchCriteria = MatchCriteria()


@dataclass(frozen=True, slots=True)
class ParentMoodDef:
    name: str
    excerpt: str
    accent: str
    classifier: MatchCriteria | None = None
    sub_moods: tuple[SubMoodDef, ...] = ()


# Single registry: order, display copy, accents, and classification rules.
PARENT_MOODS: tuple[ParentMoodDef, ...] = (
    ParentMoodDef(
        name="Dark & Stormy",
        excerpt="Uneasy atmospheres, creeping dread, and stories that keep you glancing over your shoulder.",
        accent="mood-accent-dark",
        classifier=MatchCriteria(
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
        sub_moods=(
            SubMoodDef("Supernatural", MatchCriteria(keywords_any=("supernatural", "haunted", "ghost", "demon", "paranormal", "witch"))),
            SubMoodDef("Slasher", MatchCriteria(keywords_any=("slasher", "survival horror", "masked killer"))),
            SubMoodDef("Psychological", MatchCriteria(keywords_any=("psychological", "mind game", "unreliable narrator"))),
            SubMoodDef("Serial killer", MatchCriteria(keywords_any=("serial killer", "murder investigation"))),
            SubMoodDef("Horror", MatchCriteria(genres_any=frozenset({"Horror"}))),
            SubMoodDef("Thriller", MatchCriteria(genres_any=frozenset({"Thriller"}))),
            SubMoodDef("Mystery", MatchCriteria(genres_any=frozenset({"Mystery"}))),
        ),
    ),
    ParentMoodDef(
        name="Mindbender",
        excerpt="Reality bends, timelines tangle, and the ending might send you places.",
        accent="mood-accent-mind",
        classifier=MatchCriteria(
            genres_any=frozenset({"Science Fiction", "Fantasy"}),
            keywords_any=("time travel", "dystopia", "parallel world", "dream", "simulation"),
        ),
        sub_moods=(
            SubMoodDef("Time travel", MatchCriteria(keywords_any=("time travel", "time loop", "timeline"))),
            SubMoodDef("Dystopia", MatchCriteria(keywords_any=("dystopia", "dystopian", "post-apocalyptic"))),
            SubMoodDef("Dream logic", MatchCriteria(keywords_any=("dream", "simulation", "virtual reality", "parallel world"))),
            SubMoodDef("Sci-Fi", MatchCriteria(genres_any=frozenset({"Science Fiction"}))),
            SubMoodDef("Fantasy", MatchCriteria(genres_any=frozenset({"Fantasy"}))),
        ),
    ),
    ParentMoodDef(
        name="Epic & adventurous",
        excerpt="Big skies, long journeys, and stakes that reshape kingdoms or history itself.",
        accent="mood-accent-epic",
        classifier=MatchCriteria(
            genres_any=frozenset({"War", "History", "Adventure", "Western"}),
            keywords_any=("epic", "quest", "kingdom", "battle", "empire", "based on true story"),
        ),
        sub_moods=(
            SubMoodDef("War", MatchCriteria(genres_any=frozenset({"War"}))),
            SubMoodDef("History", MatchCriteria(genres_any=frozenset({"History"}))),
            SubMoodDef("Adventure", MatchCriteria(genres_any=frozenset({"Adventure"}))),
            SubMoodDef("Western", MatchCriteria(genres_any=frozenset({"Western"}))),
            SubMoodDef("Quest", MatchCriteria(keywords_any=("quest", "journey", "expedition", "epic"))),
        ),
    ),
    ParentMoodDef(
        name="Underworld & Noir",
        excerpt="Heists, grudges, and moral gray zones where everyone has something to hide.",
        accent="mood-accent-crime",
        classifier=MatchCriteria(
            genres_any=frozenset({"Crime"}),
            keywords_any=("heist", "gangster", "detective", "film noir", "mob", "police"),
        ),
        sub_moods=(
            SubMoodDef("Heist", MatchCriteria(keywords_any=("heist", "robbery", "vault"))),
            SubMoodDef("Gangster", MatchCriteria(keywords_any=("gangster", "mob", "mafia", "organized crime"))),
            SubMoodDef("Noir", MatchCriteria(keywords_any=("film noir", "neo-noir", "detective"))),
            SubMoodDef("Police", MatchCriteria(keywords_any=("police", "cop", "investigation", "detective"))),
        ),
    ),
    ParentMoodDef(
        name="Sentimental & ice-cream worthy",
        excerpt="Chemistry, heartbreak, and the messy work of day-to-day feelings.",
        accent="mood-accent-romance",
        classifier=MatchCriteria(
            genres_any=frozenset({"Romance"}),
            keywords_any=("love story", "relationship", "breakup", "courtship"),
        ),
        sub_moods=(
            SubMoodDef("Rom-com", MatchCriteria(keywords_any=("romantic comedy", "rom-com"))),
            SubMoodDef("Heartbreak", MatchCriteria(keywords_any=("breakup", "heartbreak", "affair"))),
            SubMoodDef("Love story", MatchCriteria(keywords_any=("love story", "courtship", "relationship"))),
        ),
    ),
    ParentMoodDef(
        name="Laughs",
        excerpt="Sharp wit, absurd setups, and the kind of comedy that loosens your shoulders.",
        accent="mood-accent-laughs",
        classifier=MatchCriteria(
            genres_any=frozenset({"Comedy"}),
            keywords_any=("satire", "spoof", "workplace comedy", "buddy comedy", "romantic comedy"),
        ),
        sub_moods=(
            SubMoodDef("Satire", MatchCriteria(keywords_any=("satire", "spoof", "parody"))),
            SubMoodDef("Rom-com", MatchCriteria(keywords_any=("romantic comedy", "rom-com"))),
            SubMoodDef("Buddy comedy", MatchCriteria(keywords_any=("buddy comedy", "buddy film"))),
            SubMoodDef("Workplace", MatchCriteria(keywords_any=("workplace comedy", "office"))),
        ),
    ),
    ParentMoodDef(
        name="Cozy & Warm",
        excerpt="Warm light, gentle humor, uplifting beats, and endings that leave you lighter.",
        accent="mood-accent-cozy",
        classifier=MatchCriteria(
            genres_any=frozenset({"Family", "Animation"}),
            keywords_any=(
                "christmas",
                "holiday",
                "feel good",
                "sports",
                "dance",
                "inspirational",
                "uplifting",
                "heartwarming",
                "coming of age",
                "childhood",
                "friendship",
            ),
            keywords_block=COZY_HEAVY_SUBJECT_KEYWORDS,
            match="all",
        ),
        sub_moods=(
            SubMoodDef("Holiday", MatchCriteria(keywords_any=("christmas", "holiday", "thanksgiving"))),
            SubMoodDef(
                "Coming of age",
                MatchCriteria(
                    genres_any=frozenset({"Family", "Animation"}),
                    keywords_any=("coming of age", "childhood", "teenager"),
                    match="all",
                ),
            ),
            SubMoodDef("Animation", MatchCriteria(genres_any=frozenset({"Animation"}))),
            SubMoodDef("Family", MatchCriteria(genres_any=frozenset({"Family"}))),
            SubMoodDef("Sports", MatchCriteria(keywords_any=("sports", "athlete", "championship", "team"))),
            SubMoodDef("Inspirational", MatchCriteria(keywords_any=("inspirational", "uplifting", "underdog"))),
        ),
    ),
    ParentMoodDef(
        name="Arthouse",
        excerpt="Patient frames, odd rhythms, and films that ask you to sit with the silence.",
        accent="mood-accent-art",
        classifier=MatchCriteria(
            genres_any=frozenset({"Drama", "Documentary"}),
            keywords_any=("art house", "slow cinema", "experimental", "meditative", "festival"),
        ),
        sub_moods=(
            SubMoodDef("Documentary", MatchCriteria(genres_any=frozenset({"Documentary"}))),
            SubMoodDef("Experimental", MatchCriteria(keywords_any=("experimental", "art house", "avant-garde", "surreal"))),
            SubMoodDef("Slow cinema", MatchCriteria(keywords_any=("slow cinema", "meditative", "minimalist"))),
            SubMoodDef("Drama", MatchCriteria(genres_any=frozenset({"Drama"}))),
        ),
    ),
    ParentMoodDef(
        name="Uncategorized",
        excerpt="Watchlist gems that did not land in a clear bucket yet. Still worth a peek.",
        accent="mood-accent-neutral",
    ),
)

MOOD_ORDER: list[str] = [mood.name for mood in PARENT_MOODS]
MOOD_META: dict[str, dict[str, str]] = {
    mood.name: {"excerpt": mood.excerpt, "accent": mood.accent} for mood in PARENT_MOODS
}
FALLBACK_MOOD: str = next(mood.name for mood in PARENT_MOODS if mood.classifier is None)


@dataclass(frozen=True, slots=True)
class MoodRule:
    name: str
    genres_any: frozenset[str] = frozenset()
    keywords_any: tuple[str, ...] = ()
    genres_all: frozenset[str] = frozenset()
    keywords_block: tuple[str, ...] = ()
    match: Literal["any", "all"] = "any"


def _criteria_to_rule(name: str, criteria: MatchCriteria) -> MoodRule:
    return MoodRule(
        name=name,
        genres_any=criteria.genres_any,
        keywords_any=criteria.keywords_any,
        genres_all=criteria.genres_all,
        keywords_block=criteria.keywords_block,
        match=criteria.match,
    )


RULES: tuple[MoodRule, ...] = tuple(
    _criteria_to_rule(mood.name, mood.classifier)
    for mood in PARENT_MOODS
    if mood.classifier is not None
)

SUB_MOOD_RULES: dict[str, tuple[MoodRule, ...]] = {
    mood.name: tuple(_criteria_to_rule(sub.name, sub.criteria) for sub in mood.sub_moods)
    for mood in PARENT_MOODS
    if mood.sub_moods
}


_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def mood_slug(name: str) -> str:
    """HTML/CSS-safe slug for mood tab and filter ids (display names may contain &, etc.)."""
    slug = _SLUG_SAFE.sub("-", name.casefold()).strip("-")
    return slug or "mood"


def mood_meta(name: str) -> dict[str, str]:
    return MOOD_META.get(name, MOOD_META[FALLBACK_MOOD])


def default_sub_mood(sub_groups: dict[str, list]) -> str:
    non_general = [(name, len(films)) for name, films in sub_groups.items() if name != "General" and films]
    if non_general:
        return min(non_general, key=lambda item: item[1])[0]
    with_films = [(name, len(films)) for name, films in sub_groups.items() if films]
    if with_films:
        return max(with_films, key=lambda item: item[1])[0]
    return "General"


def _keyword_blob(keywords: list[str]) -> str:
    return " | ".join(keyword.lower() for keyword in keywords)


def _genre_set(genres: list[str]) -> set[str]:
    return {genre.strip() for genre in genres if genre.strip()}


def classify_tone(genres: list[str], keywords: list[str]) -> Tone:
    """Light vs heavy tone from combined genres and keyword signals."""
    genre_set = _genre_set(genres)
    keyword_blob = _keyword_blob(keywords)

    heavy = sum(1 for term in HEAVY_TONE_KEYWORDS if term in keyword_blob)
    if genre_set.intersection(HEAVY_TONE_GENRES):
        heavy += 2

    light = sum(1 for term in LIGHT_TONE_KEYWORDS if term in keyword_blob)

    if heavy >= 2 and heavy > light:
        return "heavy"
    if light >= 1 and light > heavy:
        return "light"
    if heavy > light:
        return "heavy"
    if light > heavy:
        return "light"
    return "neutral"


def _rule_score(
    rule: MoodRule,
    genre_set: set[str],
    keyword_blob: str,
    *,
    keyword_penalties: tuple[str, ...] = (),
) -> int | None:
    if rule.keywords_block and any(term in keyword_blob for term in rule.keywords_block):
        return None
    if rule.genres_all and not rule.genres_all.issubset(genre_set):
        return None

    genre_matches = genre_set.intersection(rule.genres_any) if rule.genres_any else set()
    genre_hit = bool(genre_matches)
    keyword_hits = [term for term in rule.keywords_any if term in keyword_blob]

    if rule.match == "all":
        if rule.genres_any and rule.keywords_any:
            if not (genre_hit and keyword_hits):
                return None
        elif rule.genres_any and not genre_hit:
            return None
        elif rule.keywords_any and not keyword_hits:
            return None
        elif not rule.genres_any and not rule.keywords_any:
            return None
    elif rule.genres_any or rule.keywords_any:
        if not genre_hit and not keyword_hits:
            return None

    score = GENRE_SCORE * len(genre_matches) + KEYWORD_SCORE * len(keyword_hits)
    for term in keyword_penalties:
        if term in keyword_blob:
            score -= PENALTY_SCORE
    return score


def _mood_rank_key(name: str) -> int:
    try:
        return MOOD_ORDER.index(name)
    except ValueError:
        return len(MOOD_ORDER)


def _score_parent_rule(
    rule: MoodRule,
    genre_set: set[str],
    keyword_blob: str,
    tone: Tone,
) -> int | None:
    allowed = MOOD_TONE_ALLOW.get(rule.name, frozenset({"heavy", "neutral", "light"}))
    if tone not in allowed:
        return None

    penalties = MOOD_KEYWORD_PENALTIES.get(rule.name, ())
    score = _rule_score(rule, genre_set, keyword_blob, keyword_penalties=penalties)
    if score is None:
        return None

    if rule.name == "Dark & Stormy" and "Comedy" in genre_set and genre_set.intersection(
        {"Horror", "Thriller", "Mystery"}
    ):
        score += GENRE_SCORE

    return score


def _pick_best_rule(
    rules: tuple[MoodRule, ...],
    genre_set: set[str],
    keyword_blob: str,
    *,
    score_fn,
    fallback: str,
) -> str:
    best_name = fallback
    best_score = 0
    best_rank = _mood_rank_key(fallback)

    for rule in rules:
        score = score_fn(rule, genre_set, keyword_blob)
        if score is None or score < MIN_MOOD_SCORE:
            continue
        rank = _mood_rank_key(rule.name)
        if score > best_score or (score == best_score and rank < best_rank):
            best_score = score
            best_name = rule.name
            best_rank = rank

    if best_score < MIN_MOOD_SCORE:
        return fallback
    return best_name


def classify_mood(genres: list[str], keywords: list[str]) -> str:
    genre_set = _genre_set(genres)
    keyword_blob = _keyword_blob(keywords)
    tone = classify_tone(genres, keywords)

    def score_fn(rule: MoodRule, gs: set[str], blob: str) -> int | None:
        return _score_parent_rule(rule, gs, blob, tone)

    return _pick_best_rule(RULES, genre_set, keyword_blob, score_fn=score_fn, fallback=FALLBACK_MOOD)


def classify_sub_mood(parent: str, genres: list[str], keywords: list[str]) -> str:
    rules = SUB_MOOD_RULES.get(parent)
    if not rules:
        return "General"

    genre_set = _genre_set(genres)
    keyword_blob = _keyword_blob(keywords)

    def score_fn(rule: MoodRule, gs: set[str], blob: str) -> int | None:
        return _rule_score(rule, gs, blob)

    return _pick_best_rule(rules, genre_set, keyword_blob, score_fn=score_fn, fallback="General")


def classify_film(genres: list[str], keywords: list[str]) -> tuple[str, str]:
    parent = classify_mood(genres, keywords)
    sub = classify_sub_mood(parent, genres, keywords)
    return parent, sub
