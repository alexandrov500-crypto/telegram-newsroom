from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewsroomStyleProfile:
    """Target voice for editorial quality checks (advisory only)."""

    key: str = "newsroom_default"
    traits: tuple[str, ...] = (
        "concise",
        "informative",
        "neutral",
        "high-signal",
        "non-clickbait",
        "mobile-readable",
    )
    max_headline_chars: int = 140
    min_headline_chars: int = 24
    ideal_summary_chars: tuple[int, int] = (80, 420)
    max_hashtags: int = 4
    min_hashtags: int = 1


DEFAULT_STYLE = NewsroomStyleProfile()
