from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from db.models import RawPost


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[\w\-]{4,}", text, flags=re.UNICODE) if len(w) >= 4}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def avg_pairwise_lexical_cohesion(posts: list[RawPost]) -> float:
    """Mean Jaccard over unordered pairs; 1.0 if <2 posts."""
    n = len(posts)
    if n < 2:
        return 1.0
    wsets = [_words(p.text or "") for p in posts]
    total = 0.0
    cnt = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += _jaccard(wsets[i], wsets[j])
            cnt += 1
    return total / cnt if cnt else 0.0


def select_cluster_for_summarization(
    posts: Iterable[RawPost],
    *,
    bucket_hours: int,
    max_posts: int,
    min_posts_fallback: int = 3,
    min_lexical_jaccard: float = 0.08,
    min_lexical_jaccard_with_last: float = 0.0,
    trim_bucket_multiplier: int = 3,
) -> list[RawPost]:
    """
    Lightweight time + lexical cohesion (no embeddings).
    - Trims very large time buckets before greedy merge to reduce unrelated merges.
    - Greedy chain: each new post must match union AND (if min_lexical_jaccard_with_last>0) last-added post.
    """
    post_list = list(posts)
    if not post_list:
        return []

    bucket_seconds = max(1, bucket_hours) * 3600
    buckets: dict[int, list[RawPost]] = defaultdict(list)
    for p in post_list:
        ts = int(p.created_at.timestamp())
        buckets[ts // bucket_seconds].append(p)

    best_key = max(buckets, key=lambda k: len(buckets[k]))
    bucket_posts = sorted(buckets[best_key], key=lambda x: x.created_at)

    cap = max(max_posts * max(2, trim_bucket_multiplier), max_posts + 1)
    if len(bucket_posts) > cap:
        bucket_posts = bucket_posts[-cap:]

    if len(bucket_posts) <= 1:
        return bucket_posts[:max_posts]

    min_overlap = max(0.01, min(min_lexical_jaccard, 0.5))
    min_last = max(0.0, min(min_lexical_jaccard_with_last, 0.5))

    selected: list[RawPost] = [bucket_posts[0]]
    union_words = _words(bucket_posts[0].text)

    for candidate in bucket_posts[1:]:
        if len(selected) >= max_posts:
            break
        cw = _words(candidate.text)
        if not cw:
            continue
        uj = _jaccard(union_words, cw)
        if uj < min_overlap:
            continue
        if min_last > 0 and selected:
            lj = _jaccard(_words(selected[-1].text), cw)
            if lj < min_last and uj < min_overlap * 1.35:
                continue
        selected.append(candidate)
        union_words |= cw

    # Do not pad the cluster with unrelated posts from the same time bucket.
    # Old behavior returned the whole bucket when greedy selection was small,
    # which merged consecutive channel posts about different stories.
    if len(selected) < min(min_posts_fallback, len(bucket_posts)):
        return selected[:max_posts]

    return selected[:max_posts]
