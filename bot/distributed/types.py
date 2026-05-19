from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NodeRole(str, Enum):
    INGEST = "ingest"
    SIGNAL = "signal"
    STORY = "story"
    DIGEST = "digest"
    PUBLISH = "publish"
    ANALYTICS = "analytics"
    OPERATOR = "operator"
    REPLAY = "replay"
    ARCHIVE = "archive"
    ALL = "all"


class NodeStatus(str, Enum):
    STARTING = "starting"
    HEALTHY = "healthy"
    DRAINING = "draining"
    OFFLINE = "offline"


class PartitionTopic(str, Enum):
    EU_GEOPOLITICAL = "eu_geopolitical"
    US_MARKET = "us_market"
    AI_TECH = "ai_tech"
    CRYPTO = "crypto"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class NodeIdentity:
    node_id: str
    role: str
    region: str = "global"
    partitions: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.node_id}:{self.role}"


@dataclass
class StoryVersionVector:
    """Optimistic concurrency vector for federated story updates."""

    story_id: int
    version: int
    node_id: str
    updated_at: str

    def bump(self) -> StoryVersionVector:
        return StoryVersionVector(
            story_id=self.story_id,
            version=self.version + 1,
            node_id=self.node_id,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class ClusterNodeRecord:
    node_id: str
    role: str
    region: str
    status: str
    is_leader: bool
    last_heartbeat_at: str
    metadata_json: str | None = None
