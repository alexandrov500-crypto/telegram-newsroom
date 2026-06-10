"""User Reality Model — composite real-world consumption, not single persona."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_TOPIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "macro": re.compile(r"(ставк|fed|cpi|gdp|inflation|инфляц|бюджет|macro|цб)", re.I),
    "crypto": re.compile(r"(bitcoin|btc|eth|crypto|биткоин|крипт|defi|stablecoin)", re.I),
    "geopolitics": re.compile(r"(sanction|санкци|war|войн|nato|геополит|дипломат|missile)", re.I),
    "ai": re.compile(r"(\bai\b|openai|nvidia|gpt|нейросет|claude|gemini|llm)", re.I),
    "markets": re.compile(r"(рынок|бирж|moex|nasdaq|fx|bond|yield|акци|oil|нефт)", re.I),
    "local": re.compile(r"(москв|росси|city|город|регион|local|муницип)", re.I),
    "tech": re.compile(r"(tech|semiconductor|chip|startup|saas|cloud|инфраструктур)", re.I),
}

_DEFAULT_AFFINITY: dict[str, float] = {
    "macro": 0.85,
    "crypto": 0.75,
    "geopolitics": 0.80,
    "ai": 0.90,
    "markets": 0.88,
    "local": 0.55,
    "tech": 0.82,
}

_DEFAULT_PRIORITY: dict[str, float] = {
    "macro": 0.80,
    "crypto": 0.70,
    "geopolitics": 0.78,
    "ai": 0.85,
    "markets": 0.88,
    "local": 0.45,
    "tech": 0.75,
}


@dataclass(frozen=True)
class UnifiedRealWorldReaderModel:
    """Heterogeneous reader: macro + crypto + geopolitics + AI + markets + local."""

    topic_affinity: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_AFFINITY))
    attention_priority: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_PRIORITY))
    analytical_dominant: bool = True
    wants_clarity_over_volume: bool = True
    avoids_multi_feed_browsing: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_affinity": dict(self.topic_affinity),
            "attention_priority": dict(self.attention_priority),
            "analytical_dominant": self.analytical_dominant,
            "wants_clarity_over_volume": self.wants_clarity_over_volume,
            "avoids_multi_feed_browsing": self.avoids_multi_feed_browsing,
        }


@dataclass(frozen=True)
class URMResult:
    topic_affinity_vector: dict[str, float]
    attention_priority_vector: dict[str, float]
    cross_topic_saturation_level: float
    daily_information_need_estimate: float
    matched_topics: tuple[str, ...]
    reader_unification_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic_affinity_vector": self.topic_affinity_vector,
            "attention_priority_vector": self.attention_priority_vector,
            "cross_topic_saturation_level": round(self.cross_topic_saturation_level, 3),
            "daily_information_need_estimate": round(self.daily_information_need_estimate, 2),
            "matched_topics": list(self.matched_topics),
            "reader_unification_score": round(self.reader_unification_score, 2),
        }


def _topic_hits(text: str) -> set[str]:
    hits: set[str] = set()
    for key, pattern in _TOPIC_PATTERNS.items():
        if pattern.search(text or ""):
            hits.add(key)
    return hits


def evaluate_user_reality(
    text: str,
    *,
    model: UnifiedRealWorldReaderModel | None = None,
    posts_today: int = 0,
) -> URMResult:
    m = model or UnifiedRealWorldReaderModel()
    hits = _topic_hits(text)
    breadth = len(hits)

    affinity_vec = {k: (v if k in hits else round(v * 0.35, 3)) for k, v in m.topic_affinity.items()}
    priority_vec = {k: (v if k in hits else round(v * 0.25, 3)) for k, v in m.attention_priority.items()}

    saturation = min(1.0, posts_today / 8.0) if posts_today else 0.0
    if breadth >= 3:
        saturation = max(0.0, saturation - 0.15)

    need = 55.0 + breadth * 8.0
    if m.avoids_multi_feed_browsing:
        need += 10.0
    need = min(100.0, need - saturation * 20.0)

    unification = 25.0 + breadth * 14.0
    if breadth >= 4:
        unification += 12.0
    unification = min(100.0, unification)

    return URMResult(
        topic_affinity_vector=affinity_vec,
        attention_priority_vector=priority_vec,
        cross_topic_saturation_level=saturation,
        daily_information_need_estimate=need,
        matched_topics=tuple(sorted(hits)),
        reader_unification_score=unification,
    )
