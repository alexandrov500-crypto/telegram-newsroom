"""Publish priority aggregation from editorial + publication signals."""

from __future__ import annotations

from typing import Any

from editorial.scoring.base import clamp01, safe_float


def compute_duplicate_confidence(
    *,
    duplicate_intel: dict[str, Any] | None,
    editorial_scores_card: dict[str, float] | None,
) -> float:
    intel = duplicate_intel or {}
    card = editorial_scores_card or {}
    max_pct = safe_float(intel.get("max_similarity_pct"), 0.0) / 100.0
    card_dup = safe_float(card.get("duplicate_confidence"), 0.0)
    return round(clamp01(max(max_pct, card_dup)), 4)


def compute_cluster_importance_score(
    *,
    cluster_size: int,
    unique_channel_count: int,
    source_convergence: float,
) -> float:
    size_part = clamp01(cluster_size / 12.0)
    channel_part = clamp01(unique_channel_count / 5.0)
    conv_part = clamp01(source_convergence)
    return round(clamp01(0.45 * size_part + 0.35 * channel_part + 0.2 * conv_part), 4)


def compute_publish_priority_score(
    *,
    publication_priority: dict[str, Any] | None,
    editorial_priority: dict[str, Any] | None,
    cluster_importance: float,
    quality_score: float,
) -> float:
    pub = publication_priority or {}
    edi = editorial_priority or {}
    candidates = [
        safe_float(pub.get("publication_priority_score"), -1.0),
        safe_float(pub.get("score"), -1.0),
        safe_float(edi.get("numeric_priority_score"), -1.0) / 100.0 if edi.get("numeric_priority_score") is not None else -1.0,
    ]
    valid = [c for c in candidates if c >= 0]
    if valid:
        base = max(valid)
    else:
        base = 0.4 * quality_score + 0.35 * cluster_importance
        lvl = str(edi.get("priority_level") or "").lower()
        if lvl in ("high", "urgent", "critical"):
            base += 0.15
        elif lvl == "low":
            base -= 0.1
    return round(clamp01(base), 4)
