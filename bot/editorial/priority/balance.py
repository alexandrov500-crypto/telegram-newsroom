from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

TOPIC_BUCKETS: dict[str, tuple[str, ...]] = {
    "geopolitical": ("ukraine-war", "war", "conflict", "geopolitics", "nato"),
    "economic": ("inflation-fed", "economy", "inflation", "jobs-labor", "fed"),
    "technology": ("ai-regulation", "openai-launches", "technology", "tech", "nvidia-chips"),
    "markets": ("markets-risk", "markets", "finance", "crypto-policy"),
    "energy": ("energy-oil", "energy", "oil"),
}


def topic_bucket(tags: Sequence[str], topic_keys: Sequence[str] | None = None) -> str:
    keys = {str(t).lower() for t in tags}
    if topic_keys:
        keys |= {str(k).lower() for k in topic_keys}
    for bucket, needles in TOPIC_BUCKETS.items():
        if keys & set(needles):
            return bucket
    return "general"


def compute_topic_balance(
    *,
    candidate_bucket: str,
    recent_buckets: Sequence[str],
) -> dict[str, float]:
    if not recent_buckets:
        return {"topic_balance_penalty": 0.0, "dominant_bucket": 0.0}
    counter = Counter(recent_buckets)
    total = len(recent_buckets)
    dominant, dom_count = counter.most_common(1)[0]
    dominant_ratio = dom_count / total
    penalty = 0.0
    if candidate_bucket == dominant and dominant_ratio >= 0.55:
        penalty = min(0.35, (dominant_ratio - 0.45) * 0.6)
    return {
        "topic_balance_penalty": round(penalty, 3),
        "dominant_bucket": round(dominant_ratio, 3),
        "bucket_counts": dict(counter),
    }
