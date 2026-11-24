from app.mood import classify_film, classify_mood, classify_tone


def test_tone_heavy_from_horror_genre_and_dark_keyword() -> None:
    assert classify_tone(["Horror", "Comedy"], ["dark", "romance"]) == "heavy"


def test_tone_light_from_satire_keywords() -> None:
    assert classify_tone(["Comedy"], ["satire", "spoof"]) == "light"


def test_comedy_horror_dark_not_laughs() -> None:
    mood, _ = classify_film(
        ["Comedy", "Horror", "Romance"],
        ["dark", "romance", "relationship"],
    )
    assert mood != "Laughs"
    assert mood == "Dark & Stormy"


def test_light_comedy_satire_is_laughs() -> None:
    mood, sub = classify_film(["Comedy"], ["satire", "spoof"])
    assert mood == "Laughs"
    assert sub == "Satire"


def test_romance_comedy_with_heartbreak_not_laughs() -> None:
    mood, _ = classify_film(
        ["Romance", "Comedy", "Drama"],
        ["heartbreak", "breakup", "relationship"],
    )
    assert mood != "Laughs"
    assert mood == "Sentimental & ice-cream worthy"


def test_scoring_prefers_stronger_dark_over_comedy_genre() -> None:
    mood, _ = classify_film(
        ["Comedy", "Thriller"],
        ["psychological", "serial killer"],
    )
    assert mood == "Dark & Stormy"
