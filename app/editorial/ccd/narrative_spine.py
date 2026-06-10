"""Weekly narrative spine — every post maps to active theme."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SPINE_THEMES: dict[str, tuple[str, ...]] = {
    "global_inflation_transition": ("inflation", "cpi", "ставк", "fed", "инфляц", "macro"),
    "ai_acceleration_cycle": ("ai", "openai", "nvidia", "gpt", "нейросет", "tech"),
    "geopolitical_fragmentation": ("sanction", "war", "nato", "геополит", "войн", "diplomat"),
    "energy_restructuring": ("oil", "gas", "opec", "energy", "нефт", "энерг"),
}

_DEFAULT_SPINE = "global_inflation_transition"


@dataclass(frozen=True)
class NarrativeSpineMatch:
    active_spine: str
    matched: bool
    theme_keywords_hit: int
    downgrade_to_digest: bool
    merge_suggested: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_spine": self.active_spine,
            "matched": self.matched,
            "theme_keywords_hit": self.theme_keywords_hit,
            "downgrade_to_digest": self.downgrade_to_digest,
            "merge_suggested": self.merge_suggested,
        }


def active_spine_for_week(*, week_offset: int = 0) -> str:
    keys = list(_SPINE_THEMES.keys())
    return keys[week_offset % len(keys)]


def evaluate_narrative_spine(
    text: str,
    *,
    active_spine: str | None = None,
    editorial_category: str = "",
) -> NarrativeSpineMatch:
    spine = active_spine or _DEFAULT_SPINE
    keywords = _SPINE_THEMES.get(spine, _SPINE_THEMES[_DEFAULT_SPINE])
    t = (text or "").lower()
    cat = (editorial_category or "").lower()

    hits = sum(1 for kw in keywords if kw in t or kw in cat)
    matched = hits >= 1

    return NarrativeSpineMatch(
        active_spine=spine,
        matched=matched,
        theme_keywords_hit=hits,
        downgrade_to_digest=not matched,
        merge_suggested=not matched and len(t.split()) < 60,
    )
