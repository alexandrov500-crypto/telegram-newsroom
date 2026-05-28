"""Editorial style profiles (prompt layer only)."""

from __future__ import annotations

# Extends ai/editorial ALLOWED_SUMMARY_STYLES when registered there.
EXTENDED_STYLE_PROMPTS: dict[str, str] = {
    "sharp-wire": (
        "Стиль: короткая проволочная заметка — первое предложение = главный факт; "
        "без вводных клише; 2–4 предложения максимум."
    ),
    "market-brief": (
        "Стиль: рыночный бриф — цифры, ставки, активы, причинно-следственные связи; "
        "без прогнозов и без «to the moon»."
    ),
    "calm-analyst": (
        "Стиль: спокойный аналитик — контекст без драмы; «что произошло → почему это важно → что дальше осторожно»."
    ),
    "cultural-digest": (
        "Стиль: культурный дайджест — человеческий тон, связки между фактами, "
        "без LinkedIn-мотивации и без engagement bait."
    ),
}


def style_prompt_block(style: str) -> str | None:
    return EXTENDED_STYLE_PROMPTS.get(style.strip().lower().replace("_", "-"))
