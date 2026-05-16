from __future__ import annotations

from typing import Any


def detect_breaking_news(
    *,
    content: str,
    sources: list[dict[str, Any]] | None,
    duplicate_intel: dict[str, Any] | None,
    priority: dict[str, Any] | None,
    recent_similar_count: int = 0,
) -> dict[str, Any]:
    """
    Heuristic breaking detector (no network). Uses urgency + multi-source + priority + duplicate burst proxy.
    """
    text = (content or "").lower()
    pri = priority or {}
    dup = duplicate_intel or {}
    score = 0.0
    reasons: list[str] = []

    if any(w in text for w in ("breaking", "urgent", "alert", "just in", "срочно")):
        score += 0.35
        reasons.append("urgency_keywords")

    uniq = len({str(s.get("channel", "")).lower() for s in (sources or []) if isinstance(s, dict)})
    if uniq >= 3:
        score += 0.22
        reasons.append("multi_source")
    elif uniq == 2:
        score += 0.12
        reasons.append("dual_source")

    pscore = float(pri.get("numeric_priority_score") or 0.0)
    if pscore >= 0.75:
        score += 0.25
        reasons.append("high_priority_score")
    elif pscore >= 0.6:
        score += 0.12
        reasons.append("elevated_priority")

    if recent_similar_count >= 2:
        score += 0.18
        reasons.append("similar_draft_burst")

    if str(dup.get("severity")) == "high":
        score += 0.08
        reasons.append("duplicate_cluster")

    score = round(max(0.0, min(1.0, score)), 4)
    is_breaking = score >= 0.62
    return {
        "is_breaking": bool(is_breaking),
        "breaking_score": score,
        "reasoning": ";".join(sorted(set(reasons)))[:400] or "no_strong_signals",
    }
