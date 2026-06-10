"""Intelligent source selection aligned to hub substitution verticals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.mpaes.hub_substitution_map import infer_vertical

# Vertical → preferred source signals (handles / patterns from registry).
_VERTICAL_SOURCE_AFFINITY: dict[str, tuple[str, ...]] = {
    "macro": ("cb_economics", "fed", "ecb", "reuters", "bloomberg", "rbc", "vedomosti"),
    "markets": ("finamalert", "bloomberg", "reuters", "moex", "markets"),
    "geopolitics": ("bbbreaking", "tass_agency", "reuters", "apnews"),
    "crypto": ("coindesk", "cointelegraph", "bloomberg"),
    "ai": ("bloomberg", "reuters", "techcrunch", "openai"),
    "energy": ("oilpricecom", "reuters", "bloomberg"),
    "business": ("bloomberg", "reutersbiz", "ft", "wsj"),
    "local": ("tass_agency", "rbc", "local"),
    "science": ("reuters", "nature", "science"),
}

_T1 = re.compile(r"(reuters|bloomberg|apnews|fed|ecb|цб|wire|official)", re.I)


@dataclass(frozen=True)
class SourceAffinityResult:
    vertical: str
    affinity_score: float
    matched_preferred: tuple[str, ...]
    tier_quality: str
    recommend_flagship: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertical": self.vertical,
            "affinity_score": round(self.affinity_score, 2),
            "matched_preferred": list(self.matched_preferred),
            "tier_quality": self.tier_quality,
            "recommend_flagship": self.recommend_flagship,
        }


def evaluate_source_affinity(
    sources: list[str],
    *,
    text: str = "",
    editorial_category: str = "",
    cluster_size: int = 1,
) -> SourceAffinityResult:
    vertical = infer_vertical(text, editorial_category)
    preferred = _VERTICAL_SOURCE_AFFINITY.get(vertical, _VERTICAL_SOURCE_AFFINITY["macro"])

    matched: list[str] = []
    t1_count = 0
    for src in sources:
        sl = (src or "").lower()
        for pref in preferred:
            if pref in sl and pref not in matched:
                matched.append(pref)
        if _T1.search(sl):
            t1_count += 1

    score = 40.0 + len(matched) * 15.0 + t1_count * 10.0 + min(15.0, cluster_size * 5.0)
    score = min(100.0, score)

    tier = "T1" if t1_count >= 1 else ("T2" if matched else "T3")
    flagship = score >= 65 and (t1_count >= 1 or cluster_size >= 2)

    return SourceAffinityResult(
        vertical=vertical,
        affinity_score=score,
        matched_preferred=tuple(matched[:5]),
        tier_quality=tier,
        recommend_flagship=flagship,
    )
