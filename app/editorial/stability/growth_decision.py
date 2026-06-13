"""Growth-aware editorial decisioning — post type, growth potential, retention."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

_POST_TYPE_BREAKING = re.compile(
    r"(breaking|срочно|urgent|экстренно|attack|взрыв|ставк.*решени|rate\s+decision)",
    re.I,
)
_POST_TYPE_DIGEST = re.compile(r"(digest|сводк|brief|итоги|утро|вечер|5\s+вещ|3\s+вещ)", re.I)
_POST_TYPE_EXPLAINER = re.compile(r"(контекст|explainer|почему\s+важ|what\s+changed|что\s+изменил)", re.I)


class PostType(str, Enum):
    BREAKING = "breaking"
    CONTEXT = "context"
    DIGEST = "digest"
    EXPLAINER = "explainer"
    NEWS = "news"


class GrowthPotential(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RetentionImpact(str, Enum):
    VIRAL = "viral"
    HABIT = "habit"
    AUTHORITY = "authority"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class GrowthDecision:
    post_type: PostType
    growth_potential: GrowthPotential
    retention_impact: RetentionImpact
    publish_immediately: bool
    schedule_slot: str
    reject: bool
    decision_reason: str
    has_what_happened: bool
    has_why_matters: bool
    has_what_next: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_type": self.post_type.value,
            "growth_potential": self.growth_potential.value,
            "retention_impact": self.retention_impact.value,
            "publish_immediately": self.publish_immediately,
            "schedule_slot": self.schedule_slot,
            "reject": self.reject,
            "decision_reason": self.decision_reason,
            "intelligence_constraint": {
                "what_happened": self.has_what_happened,
                "why_matters": self.has_why_matters,
                "what_next": self.has_what_next,
            },
        }


def _has_what_happened(text: str) -> bool:
    t = (text or "").strip()
    return len(t) >= 40 and bool(re.search(r"[.!?]", t))


def _has_why_matters(text: str) -> bool:
    t = (text or "").lower()
    return bool(
        re.search(
            r"(важн|значит|означает|matters|impact|последств|риск|влияет|why)",
            t,
        )
    )


def _has_what_next(text: str) -> bool:
    t = (text or "").lower()
    return bool(
        re.search(
            r"(дальше|следующ|expect|will|ожида|monitor|следить|next)",
            t,
        )
    )


def classify_post_type(text: str, *, is_breaking: bool = False, publishing_mode: str = "core") -> PostType:
    t = text or ""
    if is_breaking or _POST_TYPE_BREAKING.search(t):
        return PostType.BREAKING
    if publishing_mode == "editorial_synthesis" or _POST_TYPE_DIGEST.search(t):
        return PostType.DIGEST
    if _POST_TYPE_EXPLAINER.search(t):
        return PostType.EXPLAINER
    if publishing_mode == "elastic_fill":
        return PostType.CONTEXT
    return PostType.NEWS


def evaluate_growth_decision(
    text: str,
    *,
    quality_score: float = 0.0,
    is_breaking: bool = False,
    publishing_mode: str = "core",
    editorial_category: str = "",
) -> GrowthDecision:
    post_type = classify_post_type(text, is_breaking=is_breaking, publishing_mode=publishing_mode)
    wh = _has_what_happened(text)
    wy = _has_why_matters(text)
    wn = _has_what_next(text)
    intel_ok = wh and (wy or post_type in {PostType.DIGEST, PostType.EXPLAINER})

    growth = GrowthPotential.MEDIUM
    retention = RetentionImpact.NEUTRAL
    reject = False
    reason = "medium_neutral"
    immediate = False
    slot = "intraday"

    if post_type == PostType.BREAKING and quality_score >= 45:
        growth = GrowthPotential.HIGH
        retention = RetentionImpact.VIRAL
        immediate = True
        reason = "high_viral_breaking"
    elif post_type in {PostType.EXPLAINER, PostType.CONTEXT} and intel_ok:
        growth = GrowthPotential.HIGH
        retention = RetentionImpact.AUTHORITY
        slot = "context"
        reason = "high_authority_context"
    elif post_type == PostType.DIGEST:
        growth = GrowthPotential.MEDIUM
        retention = RetentionImpact.HABIT
        slot = "digest"
        reason = "habit_digest"
    elif quality_score >= 55 and intel_ok:
        growth = GrowthPotential.MEDIUM
        reason = "medium_quality_ok"
    elif quality_score < 38 and post_type == PostType.NEWS and publishing_mode == "core":
        growth = GrowthPotential.LOW
        reject = True
        reason = "low_quality_reject"
    elif not intel_ok and publishing_mode == "core" and post_type == PostType.NEWS:
        from app.editorial.stability.config import growth_intel_soft_quality_floor

        soft_floor = growth_intel_soft_quality_floor()
        if quality_score >= soft_floor and wh:
            growth = GrowthPotential.MEDIUM
            reason = "medium_quality_intel_soft_pass"
        else:
            growth = GrowthPotential.LOW
            reject = True
            reason = "missing_intelligence_constraint"

    if growth == GrowthPotential.HIGH and retention == RetentionImpact.VIRAL:
        immediate = True
    elif growth == GrowthPotential.HIGH and retention == RetentionImpact.AUTHORITY:
        immediate = False
        slot = "context"

    # Synthesis / anti-pause posts bypass hard reject
    if publishing_mode in {"elastic_fill", "editorial_synthesis"} and reject:
        reject = False
        reason = f"{reason}_anti_pause_override"
        growth = GrowthPotential.MEDIUM

    # News beat wire — clean copy has no «why matters» chrome; quality + facts suffice
    if reject and publishing_mode == "core":
        try:
            from app.editorial.ai_editorial_reviewer import autonomous_editorial_mode_enabled
            from app.editorial.news_channel_beat import news_channel_beat_enabled
            from app.editorial.stability.config import growth_intel_soft_quality_floor

            if news_channel_beat_enabled() and autonomous_editorial_mode_enabled():
                floor = growth_intel_soft_quality_floor()
                if wh and quality_score >= floor:
                    reject = False
                    growth = GrowthPotential.MEDIUM
                    reason = f"{reason}_news_beat_wire_pass"
                elif wh and quality_score >= 42 and len((text or "").strip()) >= 80:
                    reject = False
                    growth = GrowthPotential.MEDIUM
                    reason = f"{reason}_news_beat_starvation_pass"
        except Exception:
            pass

    return GrowthDecision(
        post_type=post_type,
        growth_potential=growth,
        retention_impact=retention,
        publish_immediately=immediate,
        schedule_slot=slot,
        reject=reject,
        decision_reason=reason,
        has_what_happened=wh,
        has_why_matters=wy,
        has_what_next=wn,
    )
