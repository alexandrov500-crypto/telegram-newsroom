from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.mesh.repository import MeshRepository


@dataclass
class MeshObservabilitySnapshot:
    propagation_graph: dict[str, Any] = field(default_factory=dict)
    regional_heatmap: dict[str, float] = field(default_factory=dict)
    consensus_timeline: list[dict] = field(default_factory=list)
    disagreement_map: list[dict] = field(default_factory=list)
    memory_drift: list[dict] = field(default_factory=list)
    agent_collaboration: list[dict] = field(default_factory=list)
    learning_timeline: list[dict] = field(default_factory=list)
    tournaments: list[dict] = field(default_factory=list)


class MeshObservability:
    """Cognitive mesh observability for operators and Grafana."""

    def __init__(self, repository: MeshRepository) -> None:
        self._repo = repository

    def build_snapshot(
        self,
        *,
        node_id: str,
        region: str,
        regional_pressures: dict[str, float] | None = None,
    ) -> MeshObservabilitySnapshot:
        events = self._repo.recent_events(region=region, limit=30)
        leases = self._repo.list_agent_leases(region=region)
        pending = self._repo.pending_learning_deltas(region=region)
        resilience = self._repo.get_resilience()

        propagation = {
            "node_id": node_id,
            "region": region,
            "recent_events": len(events),
            "event_types": _count_by(events, "event_type"),
            "lanes": _count_by(events, "lane"),
        }
        heatmap = regional_pressures or {region: 1.0 - resilience["mesh_health"]}
        consensus = [
            {
                "event_id": e["event_id"],
                "type": e["event_type"],
                "origin": e["origin_node"],
                "seq": e["sequence_num"],
            }
            for e in events
            if e["event_type"].startswith("reasoning.")
        ][:15]

        snap = MeshObservabilitySnapshot(
            propagation_graph=propagation,
            regional_heatmap=heatmap,
            consensus_timeline=consensus,
            disagreement_map=[],
            memory_drift=[],
            agent_collaboration=[
                {"agent_id": l["agent_id"], "holder": l["holder_node"], "region": l["region"]}
                for l in leases
            ],
            learning_timeline=[
                {"id": p["id"], "kind": p["delta_kind"], "node": p["node_id"]} for p in pending[:10]
            ],
        )
        self._repo.save_observability_snapshot(
            "mesh_full",
            {
                "propagation": propagation,
                "heatmap": heatmap,
                "resilience": resilience,
                "agents": len(leases),
            },
        )
        try:
            from bot.observability.metrics import set_mesh_health

            set_mesh_health(resilience["mesh_health"])
        except Exception:
            pass
        return snap

    def explain_conclusion(self, session_id: str) -> str:
        votes = self._repo.get_session_votes(session_id)
        if not votes:
            return f"No consensus data for session {session_id}"
        lines = [f"Consensus formation for {session_id}:"]
        for v in votes:
            lines.append(
                f"  - {v['node_id']}: vote={v['vote']:.2f} conf={v['confidence']:.2f} — {v['reason'][:60]}"
            )
        return "\n".join(lines)

    def latest_heatmap(self) -> dict[str, float] | None:
        snap = self._repo.latest_snapshot("mesh_full")
        return snap.get("heatmap") if snap else None


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key, "unknown"))
        out[k] = out.get(k, 0) + 1
    return out
