from __future__ import annotations

import hashlib
import logging

from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.types import CognitivePolicyDocument

logger = logging.getLogger(__name__)


class EditorialMemorySystem:
    """Long-term editorial memory with bounded growth and explainable recall."""

    def __init__(self, repository: CognitiveRepository, policy: CognitivePolicyDocument) -> None:
        self._repo = repository
        self._policy = policy

    @staticmethod
    def subject_key(kind: str, identifier: str) -> str:
        raw = f"{kind}:{identifier}".lower().strip()[:200]
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def remember_story(
        self,
        *,
        story_id: int,
        title: str,
        summary: str | None,
        entities: list[str] | None = None,
        region: str | None = None,
        outcome: str | None = None,
    ) -> str:
        key = self.subject_key("story", str(story_id))
        memory_id = f"story:{key}"
        self._repo.upsert_memory(
            memory_id=memory_id,
            memory_type="story_evolution",
            subject_key=key,
            title=title[:240],
            payload={
                "story_id": story_id,
                "summary": (summary or "")[:500],
                "entities": (entities or [])[:12],
                "outcome": outcome,
            },
            region=region,
        )
        return memory_id

    def remember_source(self, source: str, *, trust_delta: float, reason: str) -> None:
        key = self.subject_key("source", source)
        self._repo.upsert_memory(
            memory_id=f"source:{key}",
            memory_type="source_reputation",
            subject_key=key,
            title=source[:120],
            payload={"trust_delta": trust_delta, "reason": reason},
        )

    def remember_incident(self, incident_id: str, *, kind: str, detail: str) -> None:
        key = self.subject_key("incident", incident_id)
        self._repo.upsert_memory(
            memory_id=f"incident:{key}",
            memory_type="operational_incident",
            subject_key=key,
            title=kind,
            payload={"detail": detail[:1000]},
        )

    def recall(self, query: str, *, limit: int = 6) -> list[dict]:
        return self._repo.recall_memory(query, limit=limit)

    def context_block(self, query: str, *, limit: int = 4) -> str:
        records = self.recall(query, limit=limit)
        if not records:
            return ""
        lines = ["Editorial memory:"]
        for r in records:
            lines.append(f"- [{r['memory_type']}] {r.get('title') or r['subject_key']}")
        return "\n".join(lines)

    def maintenance(self) -> int:
        max_entries = int(self._policy.memory.get("max_entries", 50_000))
        return self._repo.prune_memory(max_entries)
