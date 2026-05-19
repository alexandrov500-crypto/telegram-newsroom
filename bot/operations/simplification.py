from __future__ import annotations

from dataclasses import dataclass

from bot.operations.ergonomics import OperationalErgonomics
from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class ConsolidatedDashboard:
    summary: str
    open_alerts: int
    top_categories: dict[str, int]
    auto_remediations: list[str]


class OperationalSimplification:
    """Alert deduplication, escalation grouping, low-risk remediation."""

    def __init__(self, repository: OperationsRepository, ergonomics: OperationalErgonomics) -> None:
        self._repo = repository
        self._ergonomics = ergonomics

    def dedupe_enqueue(
        self,
        *,
        alert_key: str,
        category: str,
        title: str,
        detail: dict | None = None,
        dedupe_hours: int = 24,
    ) -> int | None:
        if self._repo.alert_exists(alert_key, hours=dedupe_hours):
            return None
        return self._repo.enqueue_alert(
            alert_key=alert_key,
            category=category,
            title=title,
            priority=self._ergonomics.CATEGORY_PRIORITY.get(category, 40),
            detail=detail,
        )

    def consolidate_dashboard(self) -> ConsolidatedDashboard:
        alerts = self._ergonomics.triage_open(limit=50)
        groups = self._ergonomics.group_escalation(alerts)
        categories = {k: len(v) for k, v in groups.items()}
        auto: list[str] = []
        if categories.get("info", 0) > 10:
            auto.append("auto_resolve_low_priority_info_alerts")
        summary = self._ergonomics.explainability_summary(alerts[:8])
        return ConsolidatedDashboard(
            summary=summary,
            open_alerts=len(alerts),
            top_categories=categories,
            auto_remediations=auto,
        )

    def escalation_summary(self) -> str:
        alerts = self._ergonomics.triage_open()
        groups = self._ergonomics.group_escalation(alerts)
        lines = ["Escalation groups:"]
        for cat, items in sorted(groups.items(), key=lambda x: -len(x[1])):
            lines.append(f"- {cat}: {len(items)} alerts")
            if cat in ("misinformation", "epistemic") and items:
                lines.append(f"  → review required: {items[0].title[:60]}")
        return "\n".join(lines)
