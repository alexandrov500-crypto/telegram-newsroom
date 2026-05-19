from __future__ import annotations

import re

from bot.editorial.story_types import NoveltyBreakdown
from bot.processing.semantic import build_fingerprint, jaccard_similarity

_REPETITIVE_PHRASES = re.compile(
    r"\b(sources say|according to reports|it remains unclear|no comment)\b",
    re.I,
)


def compute_novelty(
    *,
    title: str,
    summary: str | None,
    prior_title: str | None,
    prior_summary: str | None,
    cluster_variant_count: int,
) -> NoveltyBreakdown:
    """Estimate how new/meaningful an update is (0–1 higher = more novel)."""
    new_fp, _ = build_fingerprint(title)
    if prior_title:
        old_fp, _ = build_fingerprint(prior_title)
        redundancy = jaccard_similarity(new_fp, old_fp)
    else:
        redundancy = 0.0

    text = f"{title} {summary or ''}"
    repetitive_penalty = 0.12 if _REPETITIVE_PHRASES.search(text) else 0.0

    update_delta = 0.55
    if prior_summary and summary:
        prior_words = set(prior_summary.lower().split())
        new_words = set(summary.lower().split())
        if prior_words:
            fresh_ratio = len(new_words - prior_words) / max(len(new_words), 1)
            update_delta = min(1.0, 0.35 + fresh_ratio * 0.65)
    elif not prior_title:
        update_delta = 0.95

    cluster_boost = min(0.15, max(0, cluster_variant_count - 1) * 0.04)
    novelty = max(
        0.0,
        min(
            1.0,
            (1.0 - redundancy) * 0.55 + update_delta * 0.35 + cluster_boost - repetitive_penalty,
        ),
    )
    return NoveltyBreakdown(
        novelty_score=novelty,
        update_delta_score=update_delta,
        redundancy_score=redundancy,
    )
