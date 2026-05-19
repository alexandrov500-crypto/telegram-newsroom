from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from bot.editorial.quality.phrases import jaccard_similarity, opening_trigram


@dataclass(frozen=True, slots=True)
class SimilarityMatch:
    pending_news_id: int
    field: str
    score: float


def find_similar_posts(
    *,
    headline: str,
    summary: str,
    tags: Sequence[str],
    recent: Sequence[dict],
    threshold: float = 0.62,
) -> list[SimilarityMatch]:
    """Compare against recent published editorial records."""
    tag_line = " ".join(str(t) for t in tags)
    matches: list[SimilarityMatch] = []
    for row in recent:
        pid = int(row.get("pending_news_id") or 0)
        if not pid:
            continue
        h_score = jaccard_similarity(headline, str(row.get("headline") or ""))
        if h_score >= threshold:
            matches.append(SimilarityMatch(pid, "headline", round(h_score, 3)))
        s_score = jaccard_similarity(summary, str(row.get("summary") or ""))
        if s_score >= threshold:
            matches.append(SimilarityMatch(pid, "summary", round(s_score, 3)))
        if opening_trigram(headline) and opening_trigram(headline) == opening_trigram(
            str(row.get("headline") or ""),
        ):
            matches.append(SimilarityMatch(pid, "opening", 1.0))
        t_score = jaccard_similarity(tag_line, " ".join(row.get("tags") or []))
        if t_score >= 0.85 and tag_line:
            matches.append(SimilarityMatch(pid, "hashtags", round(t_score, 3)))
    return matches
