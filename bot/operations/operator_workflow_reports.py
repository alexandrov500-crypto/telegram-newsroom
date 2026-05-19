from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class OperatorWorkflowReport:
    period_hours: int
    sessions: int
    actions: int
    avg_fatigue: float
    reviews: int
    useful_rate: float
    open_contradictions: int
    pending_misinfo: int
    friction_notes: list[str]

    def summary_markdown(self) -> str:
        lines = [
            f"# Operator workflow report ({self.period_hours}h)",
            "",
            f"- Sessions: **{self.sessions}**",
            f"- Actions: **{self.actions}**",
            f"- Avg fatigue: **{self.avg_fatigue:.2f}**",
            f"- Reviews: **{self.reviews}** (useful rate {self.useful_rate:.0%})",
            f"- Open contradictions: **{self.open_contradictions}**",
            f"- Pending misinfo: **{self.pending_misinfo}**",
        ]
        if self.friction_notes:
            lines.append("\n## Friction")
            for note in self.friction_notes:
                lines.append(f"- {note}")
        return "\n".join(lines)


class OperatorWorkflowReportGenerator:
    """Measure real operator behavior for continuous Telegram operation."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def build(self, *, hours: int = 24) -> OperatorWorkflowReport:
        stats = self._repo.operator_workflow_stats(hours=hours)
        friction: list[str] = []
        fatigue = float(stats.get("avg_fatigue", 0))
        if fatigue > 0.7:
            friction.append("elevated operator fatigue — consider digest batching")
        if stats.get("reviews", 0) == 0 and stats.get("sessions", 0) > 0:
            friction.append("sessions without editorial reviews recorded")
        open_c = self._repo.open_contradiction_count()
        if open_c > 15:
            friction.append(f"contradiction triage backlog ({open_c} open)")
        misinfo = self._repo.pending_misinfo_alert_count()
        if misinfo > 10:
            friction.append(f"misinformation review backlog ({misinfo} pending)")
        return OperatorWorkflowReport(
            period_hours=hours,
            sessions=int(stats.get("sessions", 0)),
            actions=int(stats.get("actions", 0)),
            avg_fatigue=fatigue,
            reviews=int(stats.get("reviews", 0)),
            useful_rate=float(stats.get("useful_rate", 0)),
            open_contradictions=open_c,
            pending_misinfo=misinfo,
            friction_notes=friction,
        )

    def usability_summary(self, *, hours: int = 24) -> dict[str, Any]:
        report = self.build(hours=hours)
        return {
            "sessions": report.sessions,
            "fatigue": report.avg_fatigue,
            "friction_count": len(report.friction_notes),
            "operable": report.avg_fatigue < 0.85 and len(report.friction_notes) < 4,
        }
