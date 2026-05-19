from __future__ import annotations

from collections import Counter
from collections.abc import Sequence


def _ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, count / total)


def compute_fatigue_metrics(
    *,
    source: str | None,
    template_key: str | None,
    tags: Sequence[str],
    tone_marker: str | None,
    recent: Sequence[dict],
) -> dict[str, float]:
    """
    Rolling fatigue scores in [0, 1]. Higher = more editorial repetition risk.
    """
    if not recent:
        return {
            "topic_fatigue": 0.0,
            "source_fatigue": 0.0,
            "template_fatigue": 0.0,
            "tone_fatigue": 0.0,
        }

    n = len(recent)
    src_key = (source or "").strip().lower()
    tpl_key = (template_key or "").strip().lower()
    tag_keys = [str(t).strip().lower() for t in tags if str(t).strip()]
    tone = (tone_marker or "").strip().lower()

    source_hits = sum(1 for r in recent if str(r.get("source") or "").lower() == src_key)
    template_hits = sum(
        1 for r in recent if str(r.get("template_key") or "").lower() == tpl_key
    )
    tone_hits = sum(
        1
        for r in recent
        if str(r.get("tone_marker") or r.get("hook") or "").lower() == tone and tone
    )

    topic_hits = 0
    if tag_keys:
        for r in recent:
            recent_tags = {str(t).lower() for t in (r.get("tags") or [])}
            if recent_tags & set(tag_keys):
                topic_hits += 1

    return {
        "topic_fatigue": round(_ratio(topic_hits, n), 3),
        "source_fatigue": round(_ratio(source_hits, n), 3),
        "template_fatigue": round(_ratio(template_hits, n), 3),
        "tone_fatigue": round(_ratio(tone_hits, n), 3),
    }


def dominant_topics(recent: Sequence[dict], *, limit: int = 5) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for row in recent:
        for tag in row.get("tags") or []:
            key = str(tag).strip().lower()
            if key:
                counter[key] += 1
    return counter.most_common(limit)
