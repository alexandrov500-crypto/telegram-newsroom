from __future__ import annotations

from dataclasses import dataclass, field

from bot.cognitive.repository import CognitiveRepository


@dataclass
class GraphSnapshot:
    nodes: list[str] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    hot_entities: list[tuple[str, float]] = field(default_factory=list)
    drift_alerts: list[str] = field(default_factory=list)


class EditorialIntelligenceGraph:
    """Cognitive substrate connecting stories, sources, evaluations, and operations."""

    def __init__(self, repository: CognitiveRepository) -> None:
        self._repo = repository

    def link(
        self,
        from_node: str,
        to_node: str,
        edge_type: str,
        *,
        weight: float = 1.0,
        metadata: dict | None = None,
    ) -> None:
        self._repo.add_graph_edge(from_node, to_node, edge_type, weight=weight, metadata=metadata)

    def link_story_evaluation(self, story_id: int, evaluation_id: str, score: float) -> None:
        self.link(f"story:{story_id}", f"eval:{evaluation_id}", "evaluated", weight=score)

    def link_story_source(self, story_id: int, source: str, trust: float) -> None:
        self.link(f"story:{story_id}", f"source:{source}", "sourced_from", weight=trust)

    def link_workflow_policy(self, workflow_id: str, policy_id: str) -> None:
        self.link(f"workflow:{workflow_id}", f"policy:{policy_id}", "governed_by")

    def neighbors(self, node_id: str, *, edge_type: str | None = None, limit: int = 50) -> list[dict]:
        return self._repo.graph_neighbors(node_id, edge_type=edge_type, limit=limit)

    def snapshot(self, focal_node: str | None = None) -> GraphSnapshot:
        edges: list[dict] = []
        if focal_node:
            edges = self.neighbors(focal_node, limit=80)
        entity_weights: dict[str, float] = {}
        for e in edges:
            if e["edge_type"] == "sourced_from":
                entity_weights[e["to_node"]] = entity_weights.get(e["to_node"], 0) + float(e["weight"])
        hot = sorted(entity_weights.items(), key=lambda x: -x[1])[:8]
        drift = []
        eval_edges = [e for e in edges if e["edge_type"] == "evaluated"]
        if eval_edges:
            avg = sum(float(e["weight"]) for e in eval_edges) / len(eval_edges)
            if avg < 0.45:
                drift.append(f"quality_drift:{focal_node}:avg={avg:.2f}")
        nodes = {e["from_node"] for e in edges} | {e["to_node"] for e in edges}
        return GraphSnapshot(nodes=sorted(nodes), edges=edges, hot_entities=hot, drift_alerts=drift)

    def lineage_query(self, node_id: str, *, depth: int = 2) -> list[dict]:
        seen = {node_id}
        frontier = [node_id]
        collected: list[dict] = []
        for _ in range(depth):
            next_frontier: list[str] = []
            for n in frontier:
                for e in self.neighbors(n, limit=30):
                    collected.append(e)
                    other = e["to_node"] if e["from_node"] == n else e["from_node"]
                    if other not in seen:
                        seen.add(other)
                        next_frontier.append(other)
            frontier = next_frontier
        return collected
