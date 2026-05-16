from __future__ import annotations

import json
from typing import Any


def _rep_mean(source_rep: dict[str, Any] | None, channels: list[str]) -> float:
    if not source_rep or not channels:
        return 0.55
    vals = []
    for ch in channels:
        key = str(ch).strip().lower()
        row = source_rep.get(key) or source_rep.get(ch) or {}
        if isinstance(row, dict) and "score" in row:
            vals.append(float(row["score"]))
    if not vals:
        return 0.55
    return sum(vals) / len(vals)


def _channels_from_sources(sources: Any) -> list[str]:
    if isinstance(sources, list):
        return [str(x.get("channel", "")).strip() for x in sources if isinstance(x, dict) and x.get("channel")]
    if isinstance(sources, str):
        try:
            data = json.loads(sources)
            if isinstance(data, list):
                return [str(x.get("channel", "")).strip() for x in data if isinstance(x, dict) and x.get("channel")]
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def compute_editorial_priority(
    content: str,
    sources: Any,
    *,
    duplicate_intel: dict[str, Any] | None = None,
    quality_scores: dict[str, Any] | None = None,
    source_reputation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dup = duplicate_intel or {}
    sev = str(dup.get("severity") or "none")
    max_sim = float(dup.get("max_similarity_pct") or 0.0)
    novelty = max(0.0, min(1.0, 1.0 - max_sim / 100.0))
    if sev == "high":
        dup_density = 0.85
    elif sev == "medium":
        dup_density = 0.55
    elif sev == "low":
        dup_density = 0.35
    else:
        dup_density = 0.1
    text = (content or "").lower()
    urgency = 0.4
    if any(w in text for w in ("breaking", "urgent", "alert", "срочно")):
        urgency = 0.92
    chans = _channels_from_sources(sources)
    diversity = min(1.0, len(set(chans)) / max(3, len(chans) or 1))
    q = quality_scores or {}
    coherence = float(q.get("coherence") or 0.6)
    conf = float(q.get("factual_confidence_heuristic") or 0.65)
    rep = _rep_mean(source_reputation if isinstance(source_reputation, dict) else None, chans)
    publish_recency = 0.55
    score = (
        0.22 * urgency
        + 0.18 * novelty
        + 0.12 * diversity
        + 0.15 * (1.0 - dup_density)
        + 0.13 * coherence
        + 0.12 * conf
        + 0.08 * rep
        + 0.05 * publish_recency
    )
    score = round(max(0.0, min(1.0, score)), 4)
    if score >= 0.78:
        level = "HIGH"
        hint = "Review soon — high attention score."
    elif score >= 0.55:
        level = "MEDIUM"
        hint = "Normal queue priority."
    else:
        level = "LOW"
        hint = "Lower urgency; verify duplicate context before publish."
    reasoning = (
        f"urgency={urgency:.2f}, novelty={novelty:.2f}, diversity={diversity:.2f}, "
        f"dup_signal={dup_density:.2f}, coherence={coherence:.2f}, conf={conf:.2f}, rep={rep:.2f}"
    )
    return {
        "priority_level": level,
        "numeric_priority_score": score,
        "reasoning": reasoning[:600],
        "moderation_hint": hint[:400],
    }
