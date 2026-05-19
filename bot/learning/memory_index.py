from __future__ import annotations

import hashlib
import re

from bot.storage.learning_repository import LearningRepository, MemoryRecord

_GEO_PATTERN = re.compile(
    r"\b(ukraine|russia|china|nato|middle east|sanction|ceasefire)\b",
    re.I,
)


class LongTermMemoryIndex:
    """Durable editorial memory for narrative precedents and patterns."""

    def __init__(self, repository: LearningRepository) -> None:
        self._repo = repository

    @staticmethod
    def memory_key(title: str, memory_type: str) -> str:
        normalized = title.lower().strip()[:120]
        payload = f"{memory_type}:{normalized}"
        return hashlib.sha256(payload.encode()).hexdigest()[:20]

    def index_story(
        self,
        *,
        title: str,
        summary: str | None,
        entities: list[str],
        memory_type: str = "narrative",
    ) -> None:
        key = self.memory_key(title, memory_type)
        self._repo.upsert_memory(
            memory_key=key,
            memory_type=memory_type,
            title=title[:240],
            summary=(summary or "")[:500] or None,
            entities=entities[:12],
        )

    def index_geopolitical_pattern(self, title: str, summary: str | None) -> None:
        text = f"{title} {summary or ''}"
        if not _GEO_PATTERN.search(text):
            return
        self.index_story(
            title=title,
            summary=summary,
            entities=[],
            memory_type="geopolitical_precedent",
        )

    def recall(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        return self._repo.recall_memory(query=query, limit=limit)

    def top_precedents(self, *, limit: int = 8) -> list[MemoryRecord]:
        return self._repo.top_memory(limit=limit)

    def context_block(self, query: str, *, limit: int = 4) -> str:
        records = self.recall(query, limit=limit)
        if not records:
            return ""
        lines = ["Long-term editorial memory:"]
        for record in records:
            lines.append(f"- [{record.memory_type}] {record.title}")
        return "\n".join(lines)
