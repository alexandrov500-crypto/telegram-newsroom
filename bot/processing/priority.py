from __future__ import annotations

import logging
import re
from typing import Any

from bot.config import get_high_trust_sources
from bot.processing.adaptive import priority_boost_from_virality
from bot.processing.source_reliability import priority_trust_adjustment

logger = logging.getLogger(__name__)

_DEFAULT_SCORE = 0.5
_HIGH_SIGNAL_THRESHOLD = 0.85

_TOPIC_BOOSTS: dict[str, float] = {
    "regulation": 0.14,
    "security": 0.12,
    "ai": 0.10,
    "crypto": 0.10,
    "government": 0.10,
    "breaking": 0.12,
}

_LOW_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcelebrity\b",
        r"\bgossip\b",
        r"\bsponsored\b",
        r"\bpromotion\b",
        r"\bpromo\b",
        r"\badvertisement\b",
        r"\bad\b",
        r"\bdeal\b",
        r"\bdiscount\b",
    )
)

_URGENCY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bbreaking\b",
        r"\burgent\b",
        r"\bapproved\b",
        r"\bban\b",
        r"\bhack\b",
        r"\boutage\b",
        r"\bcrash\b",
        r"\bemergency\b",
    )
)


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))


def _normalize_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    normalized: list[str] = []
    for tag in tags:
        token = str(tag).strip().lstrip("#").lower().replace(" ", "_")
        if token:
            normalized.append(token)
    return normalized


def _text_blob(title: str, summary: str | None) -> str:
    return f"{title} {summary or ''}".lower()


def _convergence_boost(source_count: int, cluster_variants: int) -> float:
    effective = max(source_count, cluster_variants, 1)
    if effective <= 1:
        return 0.0
    return min(0.22, 0.06 * (effective - 1))


def _topic_boost(tags: list[str]) -> tuple[float, list[str]]:
    boost = 0.0
    hits: list[str] = []
    for tag in tags:
        token = tag.lower()
        if token in _TOPIC_BOOSTS:
            boost += _TOPIC_BOOSTS[token]
            hits.append(token)
    return min(boost, 0.28), hits


def _urgency_boost(text: str) -> tuple[float, list[str]]:
    hits: list[str] = []
    for pattern in _URGENCY_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern.strip("\\b"))
    if not hits:
        return 0.0, hits
    return min(0.16, 0.04 * len(hits)), hits


def _low_value_penalty(text: str) -> tuple[float, list[str]]:
    hits: list[str] = []
    for pattern in _LOW_VALUE_PATTERNS:
        if pattern.search(text):
            hits.append("low_value")
            break
    if not hits:
        return 0.0, hits
    return 0.22, hits


def _build_reason(parts: list[str]) -> str:
    cleaned = [part for part in parts if part]
    if not cleaned:
        return "baseline editorial signal"
    return " + ".join(cleaned[:4])


def _compute_priority(
    *,
    title: str,
    summary: str | None,
    tags: list[str],
    source_count: int,
    cluster_variants: int,
    source_name: str | None,
    high_trust_sources: frozenset[str],
    source_trust: float | None = None,
    source_approval_ratio: float | None = None,
    topic_virality: float | None = None,
) -> dict[str, float | str]:
    score = _DEFAULT_SCORE
    reason_parts: list[str] = []

    convergence = _convergence_boost(source_count, cluster_variants)
    if convergence > 0:
        score += convergence
        reason_parts.append(f"{max(source_count, cluster_variants)} sources")

    topic_boost, topic_hits = _topic_boost(tags)
    if topic_boost > 0:
        score += topic_boost
        reason_parts.append(", ".join(topic_hits[:3]))

    text = _text_blob(title, summary)
    urgency_boost, urgency_hits = _urgency_boost(text)
    if urgency_boost > 0:
        score += urgency_boost
        reason_parts.append("urgency")

    if source_trust is not None and source_approval_ratio is not None:
        rep_delta, rep_reason = priority_trust_adjustment(
            trust_score=source_trust,
            approval_ratio_value=source_approval_ratio,
        )
        if rep_delta != 0.0:
            score += rep_delta
            if rep_reason:
                reason_parts.append(rep_reason)
    elif source_name and high_trust_sources:
        normalized = source_name.lower().strip()
        if any(trusted in normalized for trusted in high_trust_sources):
            score += 0.08
            reason_parts.append("trusted source")

    penalty, _ = _low_value_penalty(text)
    if penalty > 0:
        score -= penalty
        reason_parts.append("low-value signal")

    if topic_virality is not None:
        adaptive_boost = priority_boost_from_virality(float(topic_virality))
        if adaptive_boost > 0:
            score += adaptive_boost
            reason_parts.append("topic momentum")

    final_score = _clamp(score)
    reason = _build_reason(reason_parts)
    return {"score": final_score, "reason": reason}


async def calculate_priority(
    *,
    title: str,
    summary: str | None,
    tags: list[str] | None = None,
    source_count: int = 1,
    cluster_variants: int = 1,
    source_name: str | None = None,
    source_trust: float | None = None,
    source_approval_ratio: float | None = None,
    topic_virality: float | None = None,
) -> dict[str, float | str]:
    """
    Score editorial priority in [0.0, 1.0]. Never raises — fail-open to 0.5.
    """
    try:
        normalized_tags = _normalize_tags(tags or [])
        effective_sources = max(int(source_count), int(cluster_variants), 1)
        high_trust = get_high_trust_sources()

        result = _compute_priority(
            title=title or "",
            summary=summary,
            tags=normalized_tags,
            source_count=effective_sources,
            cluster_variants=max(int(cluster_variants), 1),
            source_name=source_name,
            high_trust_sources=high_trust,
            source_trust=source_trust,
            source_approval_ratio=source_approval_ratio,
            topic_virality=topic_virality,
        )
        score = float(result["score"])
        reason = str(result["reason"])

        logger.info(
            "event=priority_score_calculated score=%.3f reason=%r sources=%d variants=%d",
            score,
            reason,
            effective_sources,
            cluster_variants,
        )
        if score >= _HIGH_SIGNAL_THRESHOLD:
            logger.info(
                "event=priority_high_signal_detected score=%.3f reason=%r title=%r",
                score,
                reason,
                (title or "")[:80],
            )
        return {"score": score, "reason": reason}
    except Exception as exc:
        logger.warning("event=priority_fallback_used reason=%r", exc)
        return {"score": _DEFAULT_SCORE, "reason": "default fallback"}
