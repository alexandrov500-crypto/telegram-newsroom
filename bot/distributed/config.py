from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from bot.distributed.types import NodeIdentity, NodeRole, PartitionTopic


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True, slots=True)
class ClusterConfig:
    node_id: str
    node_role: str
    node_region: str
    event_bus_backend: str
    redis_url: str
    redis_enabled: bool
    cluster_enabled: bool
    partitions: tuple[str, ...]
    signing_key: str | None

    @property
    def identity(self) -> NodeIdentity:
        return NodeIdentity(
            node_id=self.node_id,
            role=self.node_role,
            region=self.node_region,
            partitions=self.partitions,
        )


def load_cluster_config() -> ClusterConfig:
    host = socket.gethostname().split(".")[0]
    node_id = _env("NODE_ID") or f"{host}-{os.getpid()}"
    role = _env("NODE_ROLE", NodeRole.ALL.value).lower()
    region = _env("NODE_REGION", "global").lower()
    backend = _env("EVENT_BUS_BACKEND", "inmemory").lower()
    redis_url = _env("REDIS_URL", "redis://localhost:6379/0")
    redis_on = _env("REDIS_ENABLED", "").lower() in ("1", "true", "yes", "on")
    cluster_on = _env("CLUSTER_ENABLED", "true").lower() not in ("0", "false", "no", "off")
    raw_parts = _env("NODE_PARTITIONS")
    if raw_parts:
        partitions = tuple(p.strip() for p in raw_parts.split(",") if p.strip())
    else:
        partitions = _default_partitions(role, region)
    signing = _env("CLUSTER_EVENT_SIGNING_KEY") or None
    return ClusterConfig(
        node_id=node_id,
        node_role=role,
        node_region=region,
        event_bus_backend=backend,
        redis_url=redis_url,
        redis_enabled=redis_on,
        cluster_enabled=cluster_on,
        partitions=partitions,
        signing_key=signing,
    )


def _default_partitions(role: str, region: str) -> tuple[str, ...]:
    if role in (NodeRole.SIGNAL.value, NodeRole.INGEST.value):
        if region == "eu":
            return (PartitionTopic.EU_GEOPOLITICAL.value, PartitionTopic.GLOBAL.value)
        if region == "us":
            return (PartitionTopic.US_MARKET.value, PartitionTopic.GLOBAL.value)
        return (PartitionTopic.GLOBAL.value,)
    return (PartitionTopic.GLOBAL.value,)


def role_allows_ingest(role: str) -> bool:
    return role in (NodeRole.ALL.value, NodeRole.INGEST.value)


def role_allows_digest(role: str) -> bool:
    return role in (NodeRole.ALL.value, NodeRole.DIGEST.value)


def role_allows_operator(role: str) -> bool:
    return role in (NodeRole.ALL.value, NodeRole.OPERATOR.value, NodeRole.ANALYTICS.value)


def role_allows_signals(role: str) -> bool:
    return role in (NodeRole.ALL.value, NodeRole.SIGNAL.value, NodeRole.STORY.value)
