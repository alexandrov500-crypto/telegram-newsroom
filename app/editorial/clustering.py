"""Topic clustering for editorial compression (heuristic + similarity merge)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.editorial.dedup import _jaccard, _tokenize
from app.editorial.story_types import label_story_type

_SIM_MERGE_THRESHOLD = 0.32


def _enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    text = str(item.get("text") or item.get("content") or "")
    rank = item.get("editorial_rank")
    breaking = float(item.get("breaking") or 0.0)
    if isinstance(rank, dict):
        breaking = float(rank.get("breaking") or breaking)
    st = item.get("story_type") or label_story_type(text, breaking_score=breaking)
    return {**item, "story_type": st, "text": text, "breaking": breaking}


def _merge_similar_in_group(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    cluster_tokens: list[set[str]] = []

    for it in sorted(items, key=lambda x: float(x.get("final_score") or 0.0), reverse=True):
        tokens = _tokenize(str(it.get("text") or ""))
        placed = False
        for idx, prev_tokens in enumerate(cluster_tokens):
            if _jaccard(tokens, prev_tokens) >= _SIM_MERGE_THRESHOLD:
                clusters[idx].append(it)
                cluster_tokens[idx] |= tokens
                placed = True
                break
        if not placed:
            clusters.append([it])
            cluster_tokens.append(tokens)
    return clusters


def cluster_items(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """
    Group items into story clusters.
    Primary bucket: story_type heuristic; secondary: token overlap merge.
    """
    if not items:
        return []

    enriched = [_enrich_item(it) for it in items if (it.get("text") or it.get("content"))]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in enriched:
        buckets[str(it.get("story_type") or "misc")].append(it)

    out: list[list[dict[str, Any]]] = []
    for group in buckets.values():
        out.extend(_merge_similar_in_group(group))
    return out


def cluster_score(cluster: list[dict[str, Any]]) -> float:
    if not cluster:
        return 0.0
    scores = [float(it.get("final_score") or 0.0) for it in cluster]
    return round(sum(scores) / len(scores), 4)
