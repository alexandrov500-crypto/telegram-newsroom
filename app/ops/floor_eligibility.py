"""Floor publish eligibility — cadence preservation without quality bypass."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.content_quality import (
    has_hidden_advertising,
    is_publishably_informative,
    is_truncated_mid_thought,
    passes_premium_newsroom_policy,
)

_SENTENCE_SPLIT = re.compile(r"[.!?…]+")


@dataclass(frozen=True)
class FloorEligibilityVerdict:
    eligible: bool
    score: float
    reason: str


def _sentence_count(text: str) -> int:
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    return len(parts)


def _floor_min_score() -> float:
    import os

    try:
        return max(0.55, min(0.95, float(os.getenv("FLOOR_MIN_ELIGIBILITY_SCORE", "0.72"))))
    except ValueError:
        return 0.72


def evaluate_floor_eligibility(body: str, *, sources_json: str = "") -> FloorEligibilityVerdict:
    """
    Hard rules + scoring for publishing-floor candidates.

    Floor NEVER bypasses premium policy: ``passes_premium_newsroom_policy`` is mandatory.
    """
    text = (body or "").strip()
    if not text:
        return FloorEligibilityVerdict(False, 0.0, "empty")
    if has_hidden_advertising(text):
        return FloorEligibilityVerdict(False, 0.0, "hidden_advertising")
    if is_truncated_mid_thought(text):
        return FloorEligibilityVerdict(False, 0.0, "truncated_mid_thought")
    if not is_publishably_informative(text, min_chars=120, min_sentences=2):
        return FloorEligibilityVerdict(False, 0.0, "low_informativeness")
    if not passes_premium_newsroom_policy(text):
        return FloorEligibilityVerdict(False, 0.0, "premium_policy_failed")

    score = 0.55
    sentences = _sentence_count(text)
    if sentences >= 3:
        score += 0.12
    if len(text) >= 280:
        score += 0.1
    if len(text) >= 450:
        score += 0.08
    try:
        from app.editorial.scoring_engine import score_story
        from db.repository import _channels_from_sources_json

        channels = _channels_from_sources_json(sources_json)
        escore = score_story(text=text, sources=channels, runtime_dir=None)
        score += min(0.2, float(getattr(escore, "relevance_score", 0.0) or 0.0) * 0.25)
    except Exception:
        pass

    score = round(min(1.0, score), 4)
    if score < _floor_min_score():
        return FloorEligibilityVerdict(False, score, "floor_score_below_min")
    return FloorEligibilityVerdict(True, score, "eligible")
