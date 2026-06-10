"""Audience Reality Model v2 — dynamic attention, not demographics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TOPIC = {
    "macro": re.compile(r"(fed|cpi|ставк|inflation|macro|цб|gdp)", re.I),
    "ai": re.compile(r"(\bai\b|openai|nvidia|gpt|нейросет|llm)", re.I),
    "geopolitics": re.compile(r"(sanction|war|nato|геополит|войн|missile)", re.I),
    "markets": re.compile(r"(рынок|moex|nasdaq|fx|bond|акци|бирж)", re.I),
    "crypto": re.compile(r"(bitcoin|btc|eth|crypto|крипт|defi)", re.I),
    "local": re.compile(r"(москв|город|city|local|регион|росси)", re.I),
}

_BASE_WEIGHTS = {
    "macro": 0.85,
    "ai": 0.90,
    "geopolitics": 0.78,
    "markets": 0.88,
    "crypto": 0.72,
    "local": 0.50,
}


@dataclass(frozen=True)
class ARMv2Result:
    attention_weights_dynamic: dict[str, float]
    topic_pressure_map: dict[str, float]
    daily_information_saturation: float
    content_need_prediction: float
    matched_topics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "attention_weights_dynamic": self.attention_weights_dynamic,
            "topic_pressure_map": self.topic_pressure_map,
            "daily_information_saturation": round(self.daily_information_saturation, 3),
            "content_need_prediction": round(self.content_need_prediction, 2),
            "matched_topics": list(self.matched_topics),
        }


def evaluate_audience_reality_v2(
    text: str,
    *,
    posts_today: int = 0,
    feedback_topic_weights: dict[str, float] | None = None,
) -> ARMv2Result:
    hits = {k for k, pat in _TOPIC.items() if pat.search(text or "")}
    fb = feedback_topic_weights or {}

    attn: dict[str, float] = {}
    pressure: dict[str, float] = {}
    for topic, base in _BASE_WEIGHTS.items():
        w = base
        if topic in hits:
            w = min(1.0, base + 0.12)
        if topic in fb:
            w = min(1.0, (w + float(fb[topic])) / 2.0)
        attn[topic] = round(w, 3)
        pressure[topic] = round(w * (1.2 if topic in hits else 0.4), 3)

    saturation = min(1.0, posts_today / 7.0)
    if len(hits) >= 3:
        saturation = max(0.0, saturation - 0.1)

    need = 50.0 + len(hits) * 10.0 + sum(attn[t] for t in hits) * 5.0
    need = min(100.0, need - saturation * 25.0)

    return ARMv2Result(
        attention_weights_dynamic=attn,
        topic_pressure_map=pressure,
        daily_information_saturation=saturation,
        content_need_prediction=need,
        matched_topics=tuple(sorted(hits)),
    )
