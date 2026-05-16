"""Explainable publication priority / readiness (heuristic composition)."""

from __future__ import annotations

from typing import Any


def compute_publication_priority_score(
    *,
    breaking_block: dict[str, Any] | None,
    evolution_kind: str,
    duplicate_max_pct: float,
    editorial_priority: dict[str, Any] | None,
) -> dict[str, Any]:
    brk = float((breaking_block or {}).get("breaking_score") or 0.0)
    is_brk = bool((breaking_block or {}).get("is_breaking"))
    pri_obj = editorial_priority or {}
    pri = float(pri_obj.get("priority_score") or pri_obj.get("score") or 0.5)
    dup = max(0.0, min(1.0, float(duplicate_max_pct) / 100.0))
    urgency = 0.42
    if evolution_kind == "new":
        urgency += 0.22
    elif evolution_kind == "update":
        urgency -= 0.05
    elif evolution_kind == "ambiguous":
        urgency += 0.04
    score = (
        0.32 * (1.0 - dup)
        + 0.24 * max(0.0, min(1.0, brk))
        + 0.22 * max(0.0, min(1.0, pri))
        + 0.22 * max(0.0, min(1.0, urgency))
        + (0.18 if is_brk else 0.0)
    )
    score = max(0.0, min(1.0, score))
    notes: list[str] = []
    if is_brk:
        notes.append("priority_breaking_boost")
    if dup >= 0.85:
        notes.append("priority_duplicate_drag")
    return {
        "publication_priority_score": round(score, 4),
        "components": {
            "duplicate_penalty": round(dup, 4),
            "breaking_score": round(brk, 4),
            "editorial_priority": round(pri, 4),
            "urgency": round(urgency, 4),
        },
        "notes": notes,
    }


def compute_publish_readiness_score(
    *,
    cadence_blocked: bool,
    confidence_score: float | None,
    headline_quality_score: float | None,
    unique_sources_ratio: float,
) -> dict[str, Any]:
    conf = float(confidence_score if confidence_score is not None else 0.55)
    hq = float(headline_quality_score if headline_quality_score is not None else 0.72)
    div = max(0.0, min(1.0, float(unique_sources_ratio)))
    readiness = 0.38 * conf + 0.22 * hq + 0.22 * div
    if cadence_blocked:
        readiness *= 0.55
    readiness = max(0.0, min(1.0, readiness))
    notes: list[str] = []
    if cadence_blocked:
        notes.append("readiness_cadence_penalty")
    if conf < 0.45:
        notes.append("readiness_low_confidence")
    return {
        "publish_readiness_score": round(readiness, 4),
        "components": {
            "confidence": round(conf, 4),
            "headline_quality": round(hq, 4),
            "source_diversity": round(div, 4),
            "cadence_blocked": cadence_blocked,
        },
        "notes": notes,
    }
