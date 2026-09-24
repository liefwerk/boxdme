from __future__ import annotations

from app.models import EnrichedFilm
from app.mood import mood_slug


def build_mood_explorer_css(
    grouped_films: dict[str, dict[str, list[EnrichedFilm]]],
) -> str:
    if not grouped_films:
        return ""

    lines: list[str] = []
    for mood, sub_groups in grouped_films.items():
        parent_slug = mood_slug(mood)
        lines.append(
            f".mood-explorer:has(#mood-tab-{parent_slug}:checked) "
            f'.mood-detail-panel[data-mood="{parent_slug}"] {{\n  display: block;\n}}'
        )
        lines.append(
            f".mood-explorer:has(#mood-tab-{parent_slug}:checked) "
            f'.mood-card[for="mood-tab-{parent_slug}"] {{\n'
            f"  border-color: rgba(130, 150, 180, 0.45);\n}}"
        )
        for sub_mood in sub_groups:
            sub_slug = mood_slug(sub_mood)
            lines.append(
                f'.mood-detail-panel[data-mood="{parent_slug}"]:has(#sub-{parent_slug}-{sub_slug}:checked) '
                f'.sub-mood-panel[data-sub-mood="{sub_slug}"] {{\n  display: block;\n}}'
            )
            lines.append(
                f'.mood-detail-panel[data-mood="{parent_slug}"]:has(#sub-{parent_slug}-{sub_slug}:checked) '
                f'label[for="sub-{parent_slug}-{sub_slug}"] {{\n'
                f"  border-color: rgba(74, 111, 165, 0.55);\n"
                f"  background: rgba(58, 90, 130, 0.22);\n}}"
            )
        lines.append(
            f'.mood-detail-panel[data-mood="{parent_slug}"]:has(#sub-{parent_slug}-all:checked) '
            f".sub-mood-panel {{\n  display: block;\n}}"
        )
        lines.append(
            f'.mood-detail-panel[data-mood="{parent_slug}"]:has(#sub-{parent_slug}-all:checked) '
            f'label[for="sub-{parent_slug}-all"] {{\n'
            f"  border-color: rgba(74, 111, 165, 0.55);\n"
            f"  background: rgba(58, 90, 130, 0.22);\n}}"
        )

    for n in range(0, 9):
        lines.append(
            f".mood-explorer:has(#filter-hs-{n}:checked) "
            f".film-row:not(.hs-ge-{n}) {{\n  display: none;\n}}"
        )

    return "\n".join(lines)
