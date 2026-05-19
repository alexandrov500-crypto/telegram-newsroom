from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bot.storage.signal_repository import SignalRepository


@dataclass
class CorrelationEdge:
    source_a: str
    source_b: str
    strength: float
    lag_seconds: float | None = None


@dataclass
class CorrelationGraph:
    """In-memory propagation graph with SQLite persistence."""

    narrative_key: str
    origin_source: str | None = None
    edges: list[CorrelationEdge] = field(default_factory=list)
    source_first_seen: dict[str, str] = field(default_factory=dict)

    @property
    def amplification_velocity(self) -> float:
        if not self.edges:
            return 0.0
        return min(1.0, sum(edge.strength for edge in self.edges) / max(len(self.edges), 1))


class CorrelationEngine:
    def __init__(self, repository: SignalRepository) -> None:
        self._repo = repository
        self._pending: dict[str, list[tuple[str, str]]] = defaultdict(list)

    @staticmethod
    def narrative_key(title: str, entities: list[str]) -> str:
        base = title.lower()[:80]
        if entities:
            base += "|" + "|".join(sorted(entities)[:3])
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    def record_observation(
        self,
        *,
        title: str,
        source: str | None,
        entities: list[str],
    ) -> CorrelationGraph:
        key = self.narrative_key(title, entities)
        now = datetime.now(timezone.utc).isoformat()
        src = (source or "unknown").lower()
        self._pending[key].append((src, now))

        observations = self._pending[key]
        sources = [obs[0] for obs in observations]
        unique_sources = sorted(set(sources))

        origin = unique_sources[0] if unique_sources else None
        edges: list[CorrelationEdge] = []
        for idx, other in enumerate(unique_sources[1:], start=1):
            strength = min(1.0, 0.35 + idx * 0.12)
            edges.append(
                CorrelationEdge(
                    source_a=unique_sources[0],
                    source_b=other,
                    strength=strength,
                    lag_seconds=float(idx * 300),
                ),
            )
            self._repo.save_correlation(
                narrative_key=key,
                origin_source=origin,
                source_a=unique_sources[0],
                source_b=other,
                strength=strength,
                lag_seconds=float(idx * 300),
            )

        if len(unique_sources) >= 3:
            graph = CorrelationGraph(
                narrative_key=key,
                origin_source=origin,
                edges=edges,
                source_first_seen={s: now for s, now in observations},
            )
            return graph

        return CorrelationGraph(narrative_key=key, origin_source=origin, edges=edges)
