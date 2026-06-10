"""Content Gravity System — composite score 0–100."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SHARE = re.compile(
    r"(срочно|breaking|шок|record|историческ|never\s+before|впервые|обвал|взлет|"
    r"санкци|rate\s+hike|rate\s+cut|ai\s+model|gpt)",
    re.I,
)
_NOVEL = re.compile(
    r"(новый|new\s+policy| впервые|unexpected|surprise|неожидан|breaking|срочно)",
    re.I,
)


@dataclass(frozen=True)
class GravityBreakdown:
    shareability: float
    cognitive_clarity: float
    novelty: float
    impact: float
    retention_value: float
    total: float
    tier: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "shareability": round(self.shareability, 2),
            "cognitive_clarity": round(self.cognitive_clarity, 2),
            "novelty": round(self.novelty, 2),
            "impact": round(self.impact, 2),
            "retention_value": round(self.retention_value, 2),
            "total": round(self.total, 2),
            "tier": self.tier,
            "action": self.action,
        }


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _tier_and_action(total: float) -> tuple[str, str]:
    from app.editorial.growth_dominance.config import (
        gravity_digest_only_threshold,
        gravity_must_publish_threshold,
        gravity_reject_threshold,
    )

    if total >= gravity_must_publish_threshold():
        return "must_publish", "priority_boost"
    if total >= gravity_digest_only_threshold():
        return "slot_publish", "publish_in_slot"
    if total >= gravity_reject_threshold():
        return "digest_only", "digest_merge"
    return "reject", "reject_or_synthesis"


def compute_gravity_score(
    text: str,
    *,
    quality_score: float = 0.0,
    is_breaking: bool = False,
    post_type: str = "",
    has_hook: bool = False,
    has_meaning: bool = False,
    has_implication: bool = False,
    source_independence: float = 1.0,
    publishing_mode: str = "core",
) -> GravityBreakdown:
    t = text or ""
    n = len(t)
    sentences = max(1, len(re.split(r"[.!?]+", t)))

    share = 35.0
    if _SHARE.search(t):
        share += 25.0
    if is_breaking:
        share += 20.0
    if 80 <= n <= 420:
        share += 15.0
    if post_type == "breaking":
        share += 10.0
    share = _clamp(share)

    clarity = 20.0
    if has_hook:
        clarity += 30.0
    if has_meaning:
        clarity += 25.0
    if has_implication:
        clarity += 25.0
    clarity = _clamp(clarity)

    novelty = 40.0
    if _NOVEL.search(t):
        novelty += 25.0
    if is_breaking:
        novelty += 20.0
    if sentences >= 3:
        novelty += 10.0
    novelty = _clamp(novelty)

    impact = _clamp(min(100.0, quality_score * 1.35 + (15.0 if is_breaking else 0.0)))

    retention = 35.0
    if post_type in {"digest", "explainer", "context"}:
        retention += 35.0
    if post_type == "breaking":
        retention += 15.0
    retention = _clamp(retention)

    total = (
        0.30 * share
        + 0.25 * clarity
        + 0.20 * novelty
        + 0.15 * impact
        + 0.10 * retention
    )
    total *= max(0.65, min(1.0, source_independence))
    if publishing_mode in {"elastic_fill", "editorial_synthesis"}:
        total = max(total, 45.0)
    total = _clamp(total)
    tier, action = _tier_and_action(total)
    return GravityBreakdown(
        shareability=share,
        cognitive_clarity=clarity,
        novelty=novelty,
        impact=impact,
        retention_value=retention,
        total=total,
        tier=tier,
        action=action,
    )
