from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ops_evolution.repository import OpsEvolutionRepository


@dataclass
class OperationalMemorySystem:
    """Persistent operational learning — incidents, recoveries, patterns."""

    repository: OpsEvolutionRepository

    def remember_incident(
        self,
        *,
        incident_key: str,
        summary: str,
        outcome: str = "open",
        confidence: float = 0.8,
        detail: dict[str, Any] | None = None,
    ) -> str:
        return self.repository.store_memory(
            category="incident",
            summary=summary,
            detail=detail or {},
            confidence=confidence,
            outcome=outcome,
            similarity_key=incident_key,
        )

    def remember_recovery(
        self,
        *,
        incident_key: str,
        success: bool,
        remediation: str,
    ) -> str:
        return self.repository.store_memory(
            category="recovery",
            summary=remediation[:300],
            detail={"success": success},
            confidence=0.9 if success else 0.5,
            outcome="success" if success else "failed",
            similarity_key=incident_key,
        )

    def remember_traffic_pattern(self, *, pattern: str, detail: dict[str, Any]) -> str:
        return self.repository.store_memory(
            category="traffic",
            summary=pattern,
            detail=detail,
            confidence=0.7,
            similarity_key=f"traffic:{pattern[:40]}",
        )

    def remember_quality_regression(self, *, source: str, score: float) -> str:
        return self.repository.store_memory(
            category="quality",
            summary=f"Quality regression source={source} score={score:.2f}",
            detail={"source": source, "score": score},
            confidence=0.75,
            similarity_key=f"quality:{source}",
        )

    def remember_operator_outcome(
        self,
        *,
        action: str,
        success: bool,
        detail: dict[str, Any] | None = None,
    ) -> str:
        return self.repository.store_memory(
            category="operator",
            summary=action[:200],
            detail=detail or {},
            confidence=0.85,
            outcome="success" if success else "failed",
            similarity_key=f"op:{action[:30]}",
        )

    def similar_incidents(self, incident_key: str) -> list[dict[str, Any]]:
        return self.repository.search_memory(similarity_key=incident_key, limit=10)

    def summary_text(self, *, limit: int = 8) -> str:
        rows = self.repository.search_memory(limit=limit)
        lines = ["<b>Ops memory</b>", f"Active entries (showing {len(rows)})"]
        for r in rows:
            lines.append(
                f"• [{r['category']}] {r['summary'][:60]} "
                f"(conf {r['confidence']:.2f})",
            )
        if not rows:
            lines.append("No memories stored yet.")
        return "\n".join(lines)

    def patterns_text(self) -> str:
        patterns = self.repository.recurring_patterns()
        lines = ["<b>Incident patterns</b>"]
        for p in patterns[:8]:
            lines.append(
                f"• {p['similarity_key']}: {p['c']}× "
                f"({p['category']}) conf {p['avg_conf']:.2f}",
            )
        if not patterns:
            lines.append("No recurring patterns detected.")
        return "\n".join(lines)

    def recovery_history_text(self, incident_key: str | None = None) -> str:
        if incident_key:
            rows = [
                r
                for r in self.repository.search_memory(similarity_key=incident_key, limit=20)
                if r.get("category") == "recovery"
            ]
        else:
            rows = self.repository.search_memory(category="recovery", limit=10)
        lines = ["<b>Recovery history</b>"]
        for r in rows:
            mark = "✓" if r.get("outcome") == "success" else "✗"
            lines.append(f"{mark} {r['summary'][:70]}")
        if not rows:
            lines.append("No recovery records.")
        return "\n".join(lines)
