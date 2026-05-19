from __future__ import annotations

from collections.abc import Sequence
from statistics import mean


def compute_drift_signals(
    *,
    recent_scores: Sequence[dict],
    prior_daily: Sequence[dict] | None = None,
) -> dict[str, float]:
    """
    Long-horizon drift hints. Values near 0 = stable; higher magnitude = drift.
    All outputs are advisory magnitudes in [0, 1] unless noted.
    """
    if not recent_scores:
        return {
            "tone_drift": 0.0,
            "verbosity_drift": 0.0,
            "hashtag_drift": 0.0,
            "source_diversity_drift": 0.0,
            "topic_concentration_drift": 0.0,
        }

    densities = [float(r.get("information_density") or 0) for r in recent_scores]
    verbosities = [float(r.get("verbosity") or 0) for r in recent_scores]
    hashtag_avgs = [float(r.get("hashtag_count") or 0) for r in recent_scores]

    tone_drift = 0.0
    weak_counts = [int(r.get("weak_phrase_count") or 0) for r in recent_scores]
    if len(weak_counts) >= 4:
        first = mean(weak_counts[: len(weak_counts) // 2])
        second = mean(weak_counts[len(weak_counts) // 2 :])
        tone_drift = min(1.0, abs(second - first) / 3.0)

    verbosity_drift = 0.0
    if len(verbosities) >= 4:
        first = mean(verbosities[: len(verbosities) // 2])
        second = mean(verbosities[len(verbosities) // 2 :])
        verbosity_drift = min(1.0, abs(second - first))

    hashtag_drift = 0.0
    if len(hashtag_avgs) >= 4:
        first = mean(hashtag_avgs[: len(hashtag_avgs) // 2])
        second = mean(hashtag_avgs[len(hashtag_avgs) // 2 :])
        hashtag_drift = min(1.0, abs(second - first) / 2.0)

    sources = [str(r.get("source") or "").lower() for r in recent_scores if r.get("source")]
    source_diversity_drift = 0.0
    if sources:
        unique_ratio = len(set(sources)) / len(sources)
        source_diversity_drift = round(max(0.0, 1.0 - unique_ratio), 3)

    topic_concentration_drift = 0.0
    if prior_daily:
        recent_avg = mean(densities) if densities else 0.5
        prior_avg = mean(float(p.get("avg_quality_score") or 0.5) for p in prior_daily)
        topic_concentration_drift = min(1.0, abs(recent_avg - prior_avg))

    return {
        "tone_drift": round(tone_drift, 3),
        "verbosity_drift": round(verbosity_drift, 3),
        "hashtag_drift": round(hashtag_drift, 3),
        "source_diversity_drift": round(source_diversity_drift, 3),
        "topic_concentration_drift": round(topic_concentration_drift, 3),
    }
