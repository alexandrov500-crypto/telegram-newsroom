from __future__ import annotations

from dataclasses import dataclass

from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class PrioritizedAlert:
    alert_id: int
    priority: int
    category: str
    title: str
    summary: str


class OperationalErgonomics:
    """Operator fatigue reduction and triage queues."""

    CATEGORY_PRIORITY = {
        "misinformation": 90,
        "contradiction": 80,
        "epistemic": 70,
        "cluster": 60,
        "ingestion": 50,
        "cost": 45,
        "info": 20,
    }

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def ingest_alert(
        self,
        *,
        alert_key: str,
        category: str,
        title: str,
        detail: dict | None = None,
    ) -> int:
        priority = self.CATEGORY_PRIORITY.get(category, 40)
        return self._repo.enqueue_alert(
            alert_key=alert_key,
            category=category,
            title=title,
            priority=priority,
            detail=detail,
        )

    def triage_open(self, *, limit: int = 15) -> list[PrioritizedAlert]:
        rows = self._repo.triage_queue(status="open", limit=limit)
        out: list[PrioritizedAlert] = []
        for r in rows:
            detail = r.get("detail") or {}
            summary = detail.get("explanation") or detail.get("reason") or ""
            out.append(
                PrioritizedAlert(
                    alert_id=int(r["id"]),
                    priority=int(r["priority"]),
                    category=str(r["category"]),
                    title=str(r["title"]),
                    summary=str(summary)[:200],
                )
            )
        return out

    def group_escalation(self, alerts: list[PrioritizedAlert]) -> dict[str, list[PrioritizedAlert]]:
        groups: dict[str, list[PrioritizedAlert]] = {}
        for a in alerts:
            groups.setdefault(a.category, []).append(a)
        return groups

    def explainability_summary(self, alerts: list[PrioritizedAlert]) -> str:
        if not alerts:
            return "No open operator alerts."
        lines = ["Operator triage summary:"]
        for a in alerts[:10]:
            lines.append(f"- [P{a.priority}] {a.category}: {a.title}")
            if a.summary:
                lines.append(f"    {a.summary[:100]}")
        return "\n".join(lines)

    def resolve(self, alert_id: int) -> None:
        self._repo.resolve_alert(alert_id)

    def fatigue_estimate(self, alerts_last_hour: int) -> str:
        if alerts_last_hour > 12:
            return "high_fatigue"
        if alerts_last_hour > 6:
            return "elevated"
        return "normal"
