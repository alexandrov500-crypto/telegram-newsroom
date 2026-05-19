from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from bot.production_safety.repository import ProductionSafetyRepository


class ForensicsStore:
    """Deep explainability persistence for editorial decisions."""

    def __init__(self, repository: ProductionSafetyRepository) -> None:
        self._repo = repository

    def record(
        self,
        *,
        story_id: int | None,
        trace_type: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> str:
        trace_id = f"tr_{uuid.uuid4().hex[:12]}"
        self._repo.save_forensics_trace(
            trace_id=trace_id,
            story_id=story_id,
            trace_type=trace_type,
            payload=payload,
            correlation_id=correlation_id,
        )
        return trace_id

    def story_trace_text(self, story_id: int, *, editorial: Any = None) -> str:
        traces = self._repo.get_story_traces(story_id)
        lines = [f"<b>Story trace</b> · <code>{story_id}</code>"]
        if editorial is not None:
            item = editorial.get_by_id(story_id)
            if item:
                lines.append(f"Status: {item.status} · source {item.source or '?'}")
        if not traces:
            lines.append("(no forensics traces — run cognition cycle)")
            return "\n".join(lines)
        for t in traces[:10]:
            p = t.get("payload") or {}
            summary = str(p.get("summary", p.get("decision", "")))[:120]
            lines.append(f"• [{t['trace_type']}] {summary}")
        lines.append("\n/decision_trace " + str(story_id))
        return "\n".join(lines)

    def decision_trace_text(self, story_id: int) -> str:
        traces = [t for t in self._repo.get_story_traces(story_id) if "decision" in t["trace_type"]]
        lines = [f"<b>Decision trace</b> · <code>{story_id}</code>"]
        if not traces:
            return lines[0] + "\n(no decision records)"
        for t in traces:
            p = t.get("payload") or {}
            lines.append(f"• {p.get('decision', '?')}: {p.get('reason', '')[:100]}")
            if p.get("replay_ref"):
                lines.append(f"  replay <code>{p['replay_ref']}</code>")
        return "\n".join(lines)

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]
