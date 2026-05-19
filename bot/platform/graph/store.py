from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from bot.platform.repository import PlatformRepository


@dataclass
class OperationalKnowledgeGraph:
    """Stories, sources, incidents, operators, risks — relationship graph."""

    repository: PlatformRepository
    _influence_cache: dict[str, float] = field(default_factory=dict)

    def link(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        relation: str,
        *,
        weight: float = 1.0,
    ) -> None:
        self.repository.add_graph_edge(
            from_type=from_type,
            from_id=from_id,
            to_type=to_type,
            to_id=to_id,
            relation=relation,
            weight=weight,
        )

    def story_source(self, story_id: int, source_key: str) -> None:
        self.link("story", str(story_id), "source", source_key, "sourced_from")

    def incident_story(self, incident_id: str, story_id: int) -> None:
        self.link("incident", incident_id, "story", str(story_id), "affects")

    def risk_incident(self, risk_key: str, incident_id: str) -> None:
        self.link("risk", risk_key, "incident", incident_id, "triggered")

    def influence_score(self, node_type: str, node_id: str) -> float:
        key = f"{node_type}:{node_id}"
        if key in self._influence_cache:
            return self._influence_cache[key]
        neighbors = self.repository.graph_neighbors(node_type, node_id)
        score = sum(float(n.get("weight", 0)) for n in neighbors) / max(len(neighbors), 1)
        self._influence_cache[key] = score
        return score

    def insights_text(self, node_type: str = "risk", node_id: str = "queue") -> str:
        neighbors = self.repository.graph_neighbors(node_type, node_id, limit=8)
        lines = [f"<b>Graph insights</b> {node_type}:{node_id}"]
        for n in neighbors:
            lines.append(
                f"→ {n['to_type']}:{n['to_id']} [{n['relation']}] w={n['weight']:.1f}",
            )
        if not neighbors:
            lines.append("No edges — graph will populate from ops events.")
        return "\n".join(lines)

    def risk_relations_text(self) -> str:
        import sqlite3

        with self.repository._conn() as conn:
            rows = conn.execute(
                """
                SELECT from_id, relation, COUNT(*) AS c
                FROM platform_graph_edges
                WHERE from_type = 'risk'
                GROUP BY from_id, relation ORDER BY c DESC LIMIT 8
                """,
            ).fetchall()
        lines = ["<b>Risk relations</b>"]
        for r in rows:
            lines.append(f"• {r[0]} — {r[1]} ({r[2]} links)")
        if not rows:
            lines.append("Seed: link risks via ops tick")
        return "\n".join(lines)
