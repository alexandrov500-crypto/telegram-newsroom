from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlatformObservabilityHub:
    """Unified snapshots from platform subsystems."""

    def snapshot(
        self,
        *,
        plugins: list[dict[str, Any]],
        workflows: str,
        policies: int,
        graph_edges: int,
        agent_debates: int,
    ) -> dict[str, Any]:
        return {
            "plugins_healthy": sum(1 for p in plugins if p.get("health_status") == "healthy"),
            "plugins_total": len(plugins),
            "workflows_summary": workflows,
            "policies_count": policies,
            "graph_edges": graph_edges,
            "agent_debates": agent_debates,
        }

    def platform_health_text(self, snap: dict[str, Any]) -> str:
        return (
            "<b>Platform health</b>\n"
            f"Plugins: {snap.get('plugins_healthy', 0)}/{snap.get('plugins_total', 0)} healthy\n"
            f"Policies: {snap.get('policies_count', 0)}\n"
            f"Graph edges: {snap.get('graph_edges', 0)}\n"
            f"Agent debates: {snap.get('agent_debates', 0)}"
        )

    def topology_text(self, snap: dict[str, Any]) -> str:
        return (
            "<b>Topology snapshot</b>\n"
            "Layers: ingest → cognition → moderation → publish\n"
            "Platform: plugins | workflow | policy | graph | gateway\n"
            f"Status: {snap.get('plugins_healthy', 0)} plugins OK · "
            f"{snap.get('graph_edges', 0)} graph links"
        )
