from __future__ import annotations

import re

from bot.distributed.types import PartitionTopic

_TAG_ROUTES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(crypto|bitcoin|ethereum|defi)\b", re.I), PartitionTopic.CRYPTO.value),
    (re.compile(r"\b(ai|artificial intelligence|openai|nvidia|semiconductor)\b", re.I), PartitionTopic.AI_TECH.value),
    (re.compile(r"\b(fed|nasdaq|s&p|wall street|treasury|inflation)\b", re.I), PartitionTopic.US_MARKET.value),
    (re.compile(r"\b(nato|ukraine|russia|eu|brussels|sanctions)\b", re.I), PartitionTopic.EU_GEOPOLITICAL.value),
)


def route_partition(
    *,
    title: str,
    tags: tuple[str, ...] = (),
    region: str = "global",
) -> str:
    """Topic-based routing for signal ingestion partitions."""
    haystack = f"{title} {' '.join(tags)}"
    for pattern, topic in _TAG_ROUTES:
        if pattern.search(haystack):
            return topic
    if region == "us":
        return PartitionTopic.US_MARKET.value
    if region == "eu":
        return PartitionTopic.EU_GEOPOLITICAL.value
    return PartitionTopic.GLOBAL.value


def node_owns_partition(
    node_partitions: tuple[str, ...],
    partition_key: str,
) -> bool:
    if not node_partitions:
        return True
    return partition_key in node_partitions or PartitionTopic.GLOBAL.value in node_partitions
