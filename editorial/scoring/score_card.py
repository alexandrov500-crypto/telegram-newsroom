"""Rule-based editorial scoring (deterministic heuristics)."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from db.models import RawPost

from editorial.models import EditorialScoreCard


def _age_hours(created_at: datetime) -> float:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - created_at
    return max(0.0, delta.total_seconds() / 3600.0)


def compute_editorial_score_card(
    *,
    draft_text: str,
    raw_posts: list[RawPost],
    quality_scores: dict[str, Any] | None,
    cluster_size: int,
) -> EditorialScoreCard:
    """Return normalized scores in ``[0, 1]`` (higher = better except spam/duplicate)."""
    q = quality_scores or {}
    uniq = float(q.get("uniqueness_ratio") or 0.5)
    src_cov = float(q.get("sources_ratio") or 0.5)
    ages = [_age_hours(p.created_at) for p in raw_posts] if raw_posts else [0.0]
    min_age_h = min(ages) if ages else 0.0
    freshness = max(0.0, min(1.0, math.exp(-min_age_h / 12.0)))
    chans = {str(p.channel_name).lower() for p in raw_posts}
    source_reliability = max(0.0, min(1.0, 0.35 + 0.12 * len(chans) + 0.04 * min(cluster_size, 8)))
    wc = len(re.findall(r"\w+", draft_text))
    topic_importance = max(0.0, min(1.0, 0.25 + 0.35 * min(1.0, wc / 220.0) + 0.15 * min(1.0, cluster_size / 6.0)))
    spam_signals = 0
    low = draft_text.lower()
    if re.search(r"\b(viagra|casino|crypto airdrop|click here|100% free)\b", low):
        spam_signals += 1
    if len(re.findall(r"!{3,}", draft_text)) >= 2:
        spam_signals += 1
    spam_likelihood = max(0.0, min(1.0, 0.15 * spam_signals))
    dup_conf = max(0.0, min(1.0, 1.0 - uniq))
    ai_conf = max(0.0, min(1.0, 0.45 * uniq + 0.35 * src_cov + 0.15 * min(1.0, wc / 180.0)))
    return EditorialScoreCard(
        freshness=round(freshness, 4),
        source_reliability=round(source_reliability, 4),
        topic_importance=round(topic_importance, 4),
        spam_likelihood=round(spam_likelihood, 4),
        duplicate_confidence=round(dup_conf, 4),
        ai_confidence_estimate=round(ai_conf, 4),
    )
