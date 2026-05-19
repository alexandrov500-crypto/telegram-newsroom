from __future__ import annotations

import logging
from itertools import combinations

try:
    import networkx as nx
except ImportError:  # pragma: no cover - optional at import; required in prod
    nx = None  # type: ignore[assignment]

from bot.storage.story_repository import StoryRepository

logger = logging.getLogger(__name__)


class EntityGraph:
    """Lightweight co-occurrence graph backed by networkx + SQLite edges."""

    def __init__(self, repository: StoryRepository) -> None:
        self._repo = repository
        self._graph = nx.Graph() if nx is not None else None

    def record_entities(
        self,
        entity_names: list[str],
        *,
        story_id: int | None = None,
    ) -> None:
        clean = sorted({name.strip().lower() for name in entity_names if name.strip()})
        if len(clean) < 2:
            return
        if self._graph is not None:
            for name in clean:
                self._graph.add_node(name)
            for left, right in combinations(clean, 2):
                if self._graph.has_edge(left, right):
                    self._graph[left][right]["weight"] = (
                        self._graph[left][right].get("weight", 0.0) + 1.0
                    )
                else:
                    self._graph.add_edge(left, right, weight=1.0)
        try:
            for left, right in combinations(clean, 2):
                self._repo.upsert_relationship(
                    left_entity=left,
                    right_entity=right,
                    weight_delta=1.0,
                    story_id=story_id or 0,
                )
        except Exception:
            logger.exception("event=entity_graph_persist_failed story_id=%s", story_id)

    def neighbors(self, entity: str, *, limit: int = 6) -> list[tuple[str, float]]:
        key = entity.strip().lower()
        if self._graph is None or key not in self._graph:
            return []
        pairs: list[tuple[str, float]] = []
        for neighbor in self._graph.neighbors(key):
            weight = float(self._graph[key][neighbor].get("weight", 1.0))
            pairs.append((neighbor, weight))
        pairs.sort(key=lambda item: (-item[1], item[0]))
        return pairs[:limit]
