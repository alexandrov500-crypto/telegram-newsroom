from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ops_evolution.memory.operational import OperationalMemorySystem
from bot.ops_evolution.repository import OpsEvolutionRepository


@dataclass
class OperatorKnowledgeAssistant:
    """Grounded ops Q&A — citations from internal records only."""

    repository: OpsEvolutionRepository
    memory: OperationalMemorySystem

    def answer(self, question: str, *, signals: dict[str, Any] | None = None) -> str:
        q = question.lower().strip()
        citations: list[str] = []
        lines = ["<b>Ops assistant</b>"]

        if "incident" in q or "alert" in q:
            rows = self.memory.repository.search_memory(category="incident", limit=5)
            if rows:
                lines.append("Recent incidents (internal):")
                for r in rows:
                    lines.append(f"• {r['summary'][:80]}")
                    citations.append(f"mem:{r['memory_id'][:8]}")
            else:
                lines.append("No incident memories on record.")
        elif "risk" in q or "forecast" in q:
            sig = signals or {}
            lines.append(
                f"Latest signals: queue {sig.get('queue_depth', '?')}, "
                f"quality {sig.get('quality_avg', '?')}",
            )
            citations.append("signals:live")
        elif "quality" in q:
            rows = self.memory.repository.search_memory(category="quality", limit=5)
            for r in rows:
                lines.append(f"• {r['summary'][:80]}")
                citations.append(f"mem:{r['memory_id'][:8]}")
        elif "recovery" in q:
            lines.append(self.memory.recovery_history_text())
            citations.append("mem:recovery")
        else:
            patterns = self.repository.recurring_patterns(min_count=2)
            if patterns:
                lines.append("Recurring patterns:")
                for p in patterns[:4]:
                    lines.append(f"• {p['similarity_key']} ({p['c']}×)")
                citations.append("mem:patterns")
            else:
                lines.append(
                    "I can explain incidents, risk, quality, recovery. "
                    "Try: /ops_assistant why did queue spike",
                )

        if citations:
            lines.append(f"\n<i>Sources: {', '.join(citations[:5])}</i>")
        lines.append("<i>Grounded in internal telemetry only.</i>")
        return "\n".join(lines)

    def explain_alert(self, alert_id: str, *, signals: dict[str, Any] | None = None) -> str:
        rows = self.memory.repository.search_memory(similarity_key=alert_id, limit=5)
        if not rows:
            rows = self.memory.repository.search_memory(limit=10)
            rows = [r for r in rows if alert_id in r.get("summary", "")]
        if not rows:
            return (
                f"No internal record for <code>{alert_id}</code>. "
                "Check /incident_review or /system_risk."
            )
        lines = [f"<b>Alert explain</b> <code>{alert_id}</code>"]
        for r in rows[:3]:
            lines.append(f"• {r['category']}: {r['summary'][:100]}")
            if r.get("outcome"):
                lines.append(f"  outcome: {r['outcome']}")
        similar = self.repository.recurring_patterns()
        rel = [p for p in similar if alert_id in str(p.get("similarity_key", ""))]
        if rel:
            lines.append(f"Recurring: {rel[0]['c']} occurrences")
        lines.append("→ /recovery_history · /ops_advisor")
        return "\n".join(lines)
