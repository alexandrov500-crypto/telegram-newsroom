from __future__ import annotations

from collections import Counter
from typing import Any


def attribute_starvation_causes(
    totals: Counter[str] | dict[str, int],
    rejects: Counter[str] | dict[str, int],
) -> dict[str, Any]:
    """Weighted heuristic attribution — explainable, no ML."""
    if isinstance(totals, Counter):
        t = totals
    else:
        t = Counter(totals)
    if isinstance(rejects, Counter):
        r = rejects
    else:
        r = Counter(rejects)

    fetched = max(1, int(t.get("FETCHED", 0)))
    published = int(t.get("PUBLISHED", 0))
    clustered = int(t.get("CLUSTERED", 0))
    deduped = int(t.get("DEDUPED", 0))
    quarantined = int(t.get("QUARANTINED", 0))
    quality_held = sum(v for k, v in r.items() if "quality" in k or "trust" in k)
    fatigue_held = sum(v for k, v in r.items() if "fatigue" in k)

    raw = {
        "cluster_absorption": clustered / fetched,
        "dedupe_strict": deduped / fetched,
        "quality_gate": (quarantined + quality_held) / fetched,
        "fatigue_suppression": fatigue_held / max(1, fetched),
        "low_enqueue": max(0, 1.0 - (int(t.get("QUALITY_PASSED", 0)) / fetched)),
        "publish_blocked": quarantined / max(1, published + quarantined) if quarantined else 0,
    }

    total_weight = sum(raw.values()) or 1.0
    weights = {k: round(v / total_weight, 3) for k, v in raw.items() if v > 0}
    dominant = max(weights, key=weights.get) if weights else None

    return {
        "weights": weights,
        "dominant_cause": dominant,
        "summary": _format_summary(weights),
    }


def _format_summary(weights: dict[str, float]) -> str:
    if not weights:
        return "insufficient_funnel_data"
    parts = sorted(weights.items(), key=lambda x: -x[1])[:3]
    return ", ".join(f"{k}={v:.0%}" for k, v in parts)
