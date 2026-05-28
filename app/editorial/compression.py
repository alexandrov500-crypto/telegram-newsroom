"""Editorial compression — information budget and cluster/item pruning."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from app.editorial.clustering import cluster_items, cluster_score
from app.editorial.dedup import collapse_topic_duplicates, dedupe_within_cluster
from app.editorial.story_types import StoryType

_MAX_ITEMS = int(os.getenv("EDITORIAL_MAX_ITEMS", "7"))
_MAX_CLUSTERS = int(os.getenv("EDITORIAL_MAX_CLUSTERS", "3"))
_MAX_PER_CLUSTER = int(os.getenv("EDITORIAL_MAX_PER_CLUSTER", "2"))
_MIN_SIGNAL = float(os.getenv("EDITORIAL_MIN_ITEM_SCORE", "0.55"))

_FILLER = re.compile(
    r"(мем|meme|lol|прикол|шутк|фитнес|fitness|тренер|lifestyle)",
    re.I,
)


@dataclass
class CompressedCluster:
    items: list[dict[str, Any]]
    cluster_score: float
    story_type: str
    rank: int = 0


def _is_filler(item: dict[str, Any]) -> bool:
    return bool(_FILLER.search(str(item.get("text") or "")))


def _viral_exception(item: dict[str, Any]) -> bool:
    return float(item.get("breaking") or 0.0) >= 0.7 or float(item.get("final_score") or 0.0) >= 0.8


def compress_clusters(
    clusters: list[list[dict[str, Any]]],
    *,
    max_clusters: int = _MAX_CLUSTERS,
    max_items: int = _MAX_ITEMS,
    max_per_cluster: int = _MAX_PER_CLUSTER,
    min_signal: float = _MIN_SIGNAL,
) -> list[CompressedCluster]:
    """
    Score clusters, keep top N, prune low-signal and filler items.
    """
    scored: list[CompressedCluster] = []
    for cl in clusters:
        if not cl:
            continue
        deduped = dedupe_within_cluster(cl)
        pruned: list[dict[str, Any]] = []
        for it in sorted(deduped, key=lambda x: float(x.get("final_score") or 0.0), reverse=True):
            fs = float(it.get("final_score") or 0.0)
            if fs < min_signal and not _viral_exception(it):
                continue
            if _is_filler(it) and not _viral_exception(it):
                continue
            pruned.append(it)
            if len(pruned) >= max_per_cluster:
                break
        if not pruned:
            continue
        dominant = max(pruned, key=lambda x: float(x.get("final_score") or 0.0))
        scored.append(
            CompressedCluster(
                items=pruned,
                cluster_score=cluster_score(pruned),
                story_type=str(dominant.get("story_type") or StoryType.MISC.value),
            )
        )

    scored.sort(key=lambda c: c.cluster_score, reverse=True)

    breaking_first: list[CompressedCluster] = []
    rest: list[CompressedCluster] = []
    for c in scored:
        if c.story_type == StoryType.BREAKING.value:
            breaking_first.append(c)
        else:
            rest.append(c)

    ordered = breaking_first[:1] + rest
    kept_clusters: list[CompressedCluster] = []
    total_items = 0
    for idx, c in enumerate(ordered[:max_clusters]):
        room = max_items - total_items
        if room <= 0:
            break
        items = c.items[: min(len(c.items), max_per_cluster, room)]
        if not items:
            continue
        kept_clusters.append(
            CompressedCluster(
                items=items,
                cluster_score=c.cluster_score,
                story_type=c.story_type,
                rank=idx + 1,
            )
        )
        total_items += len(items)

    return kept_clusters
