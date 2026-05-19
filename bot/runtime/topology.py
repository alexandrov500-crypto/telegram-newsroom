from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TopologySnapshot:
    health_score: float
    nodes: list[dict[str, Any]] = field(default_factory=list)
    regions: dict[str, dict[str, Any]] = field(default_factory=dict)
    partitions: list[dict[str, Any]] = field(default_factory=list)
    stream_health: dict[str, Any] = field(default_factory=dict)
    workflow_ownership: list[dict[str, Any]] = field(default_factory=list)
    lease_holders: dict[str, str] = field(default_factory=dict)
    replay_pressure: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    hot_partitions: list[str] = field(default_factory=list)
    unhealthy_nodes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": self.health_score,
            "nodes": self.nodes,
            "regions": self.regions,
            "partitions": self.partitions,
            "stream_health": self.stream_health,
            "workflow_ownership": self.workflow_ownership,
            "lease_holders": self.lease_holders,
            "replay_pressure": self.replay_pressure,
            "recommendations": self.recommendations,
            "hot_partitions": self.hot_partitions,
            "unhealthy_nodes": self.unhealthy_nodes,
        }


class TopologyIntelligence:
    """Live cluster graph and rebalance recommendations."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def build_snapshot(
        self,
        *,
        coordination: Any,
        signals: Any | None = None,
        leader: str | None = None,
    ) -> TopologySnapshot:
        nodes_raw = coordination.list_nodes(include_stale=True)
        partitions = coordination.list_partitions()
        nodes = [
            {
                "node_id": n.node_id,
                "role": n.role,
                "region": n.region,
                "status": n.status,
                "last_heartbeat": n.last_heartbeat_at,
            }
            for n in nodes_raw
        ]
        regions: dict[str, dict[str, Any]] = {}
        unhealthy: list[str] = []
        for n in nodes:
            reg = str(n["region"])
            bucket = regions.setdefault(reg, {"healthy": 0, "total": 0, "score": 1.0})
            bucket["total"] += 1
            if n["status"] == "healthy":
                bucket["healthy"] += 1
            else:
                unhealthy.append(str(n["node_id"]))
        for reg, bucket in regions.items():
            bucket["score"] = bucket["healthy"] / max(bucket["total"], 1)

        hot = [
            str(p["partition_key"])
            for p in partitions
            if int(p.get("lag_events") or 0) > 50 or p.get("paused")
        ]
        recommendations: list[str] = []
        if unhealthy:
            recommendations.append(f"investigate nodes: {', '.join(unhealthy[:5])}")
        if hot:
            recommendations.append(f"rebalance hot partitions: {', '.join(hot[:3])}")
        low_regions = [r for r, b in regions.items() if b["score"] < 0.5]
        if low_regions:
            recommendations.append(f"regional failover candidates: {', '.join(low_regions)}")

        stream_health = {}
        replay_pressure = {}
        if signals is not None:
            stream_health = {
                "lag_sec": getattr(signals, "stream_lag_sec", 0),
                "dlq": getattr(signals, "dlq_count", 0),
                "pending": getattr(signals, "pending_stream", 0),
            }
            replay_pressure = {"backlog": getattr(signals, "replay_backlog", 0)}

        health = 1.0
        if nodes:
            health = sum(1 for n in nodes if n["status"] == "healthy") / len(nodes)
        if stream_health.get("dlq", 0) > 50:
            health *= 0.8
        if stream_health.get("lag_sec", 0) > 30:
            health *= 0.85

        snap = TopologySnapshot(
            health_score=round(health, 3),
            nodes=nodes,
            regions=regions,
            partitions=[dict(p) for p in partitions],
            stream_health=stream_health,
            lease_holders={"cluster_leader": leader or ""},
            replay_pressure=replay_pressure,
            recommendations=recommendations,
            hot_partitions=hot,
            unhealthy_nodes=unhealthy,
        )
        self._persist(snap)
        return snap

    def _persist(self, snap: TopologySnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO topology_snapshots (snapshot_json, health_score, created_at)
                VALUES (?, ?, ?)
                """,
                (json.dumps(snap.to_dict()), snap.health_score, self._now()),
            )
            conn.commit()

    def latest(self) -> TopologySnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT snapshot_json, health_score FROM topology_snapshots
                ORDER BY id DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        data = json.loads(row["snapshot_json"])
        return TopologySnapshot(
            health_score=float(row["health_score"]),
            nodes=data.get("nodes", []),
            regions=data.get("regions", {}),
            partitions=data.get("partitions", []),
            stream_health=data.get("stream_health", {}),
            workflow_ownership=data.get("workflow_ownership", []),
            lease_holders=data.get("lease_holders", {}),
            replay_pressure=data.get("replay_pressure", {}),
            recommendations=data.get("recommendations", []),
            hot_partitions=data.get("hot_partitions", []),
            unhealthy_nodes=data.get("unhealthy_nodes", []),
        )
