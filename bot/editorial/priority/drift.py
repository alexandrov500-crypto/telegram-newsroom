from __future__ import annotations

from collections import Counter
from collections.abc import Sequence


def analyze_priority_drift(recent: Sequence[dict]) -> dict[str, float | str | dict]:
    """Newsroom-level priority governance signals (advisory)."""
    if not recent:
        return {
            "noise_ratio": 0.0,
            "avg_priority": 0.5,
            "routine_share": 0.0,
            "breaking_share": 0.0,
            "topic_imbalance": 0.0,
            "drift_alert": "stable",
        }
    scores = [float(r.get("editorial_priority_score") or 0) for r in recent]
    urgencies = [str(r.get("urgency_class") or "routine") for r in recent]
    avg = sum(scores) / len(scores)
    low = sum(1 for s in scores if s < 0.4) / len(scores)
    routine = sum(1 for u in urgencies if u in ("routine", "background", "low-priority")) / len(
        urgencies,
    )
    breaking = sum(1 for u in urgencies if u == "breaking") / len(urgencies)
    buckets = Counter(str(r.get("topic_bucket") or "general") for r in recent)
    total = len(recent)
    dominant_ratio = buckets.most_common(1)[0][1] / total if buckets else 0.0

    alert = "stable"
    if low >= 0.45:
        alert = "rising_noise"
    elif breaking >= 0.35:
        alert = "overbreaking"
    elif avg < 0.42:
        alert = "quality_drift_down"
    elif dominant_ratio >= 0.6:
        alert = "topic_imbalance"

    return {
        "noise_ratio": round(low, 3),
        "avg_priority": round(avg, 3),
        "routine_share": round(routine, 3),
        "breaking_share": round(breaking, 3),
        "topic_imbalance": round(dominant_ratio, 3),
        "bucket_counts": dict(buckets),
        "drift_alert": alert,
    }
