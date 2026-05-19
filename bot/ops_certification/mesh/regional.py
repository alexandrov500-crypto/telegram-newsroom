from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RegionalNodeHealth:
    node_id: str
    region: str
    healthy: bool
    last_seen: float
    quarantined: bool = False
    is_leader: bool = False


@dataclass
class RegionalMeshFoundation:
    """
    Cross-region / multi-node primitives (not full K8s).
    Leader election, health aggregation, quarantine, replay safety hints.
    """

    local_node_id: str
    local_region: str = "global"
    _nodes: dict[str, RegionalNodeHealth] = field(default_factory=dict)
    _leader_id: str | None = None

    def register_peer(
        self,
        node_id: str,
        *,
        region: str = "global",
        healthy: bool = True,
        is_leader: bool = False,
    ) -> None:
        self._nodes[node_id] = RegionalNodeHealth(
            node_id=node_id,
            region=region,
            healthy=healthy,
            last_seen=time.monotonic(),
            is_leader=is_leader,
        )
        if is_leader:
            self._leader_id = node_id

    def heartbeat_local(self, *, healthy: bool = True) -> None:
        self.register_peer(
            self.local_node_id,
            region=self.local_region,
            healthy=healthy,
            is_leader=self._leader_id == self.local_node_id,
        )

    def quarantine_node(self, node_id: str) -> None:
        n = self._nodes.get(node_id)
        if n is not None:
            n.quarantined = True
            n.healthy = False
            logger.warning("event=mesh_node_quarantine node=%s", node_id)

    def aggregate_health(self) -> dict[str, Any]:
        now = time.monotonic()
        stale = [n for n in self._nodes.values() if now - n.last_seen > 120]
        healthy = [n for n in self._nodes.values() if n.healthy and not n.quarantined]
        return {
            "leader": self._leader_id,
            "nodes_total": len(self._nodes),
            "healthy_count": len(healthy),
            "stale_count": len(stale),
            "quarantined": [n.node_id for n in self._nodes.values() if n.quarantined],
            "cross_region_replay_safe": len(stale) == 0,
        }

    def sync_from_cluster(
        self,
        *,
        leader: str | None,
        node_id: str,
        region: str,
    ) -> None:
        self._leader_id = leader
        self.local_node_id = node_id
        self.local_region = region
        self.heartbeat_local(healthy=True)

    def summary_text(self) -> str:
        agg = self.aggregate_health()
        lines = [
            "<b>Regional mesh</b>",
            f"Leader: <code>{agg['leader'] or 'none'}</code>",
            f"Nodes {agg['nodes_total']} · healthy {agg['healthy_count']}",
            f"Stale {agg['stale_count']} · quarantined {len(agg['quarantined'])}",
        ]
        return "\n".join(lines)
