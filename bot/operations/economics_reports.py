from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.operations.repository import OperationsRepository
from bot.operations.types import ProductionSLOs


@dataclass(frozen=True)
class DailyCostReport:
    report_date: str
    total_usd: float
    breakdown: dict[str, float]
    anomaly: bool
    cognition_roi_hint: str


class ProductionEconomicsReports:
    """Daily cost reports, budgets, and throttling profiles."""

    LOW_COST_PROFILE = {
        "max_llm_depth": "shallow",
        "simulation_quota": 0,
        "replay_rate_limit": 10,
        "federation_bandwidth": 0.3,
    }

    def __init__(self, repository: OperationsRepository, slos: ProductionSLOs | None = None) -> None:
        self._repo = repository
        self._slos = slos or ProductionSLOs()

    def generate_daily_report(
        self,
        *,
        token: float,
        replay: float,
        cognition: float,
        federation: float,
        publishes: int = 0,
    ) -> DailyCostReport:
        day = datetime.now(timezone.utc).date().isoformat()
        total = token + replay + cognition + federation
        breakdown = {
            "token": token,
            "replay": replay,
            "cognition": cognition,
            "federation": federation,
        }
        anomaly = total > self._slos.openai_daily_budget_usd * 0.9
        roi = "favorable" if publishes > 0 and total / max(publishes, 1) < 0.5 else "review"
        self._repo.save_daily_cost_report(day, total, breakdown, anomaly=anomaly)
        if anomaly:
            self._repo.enqueue_alert(
                alert_key=f"cost:daily:{day}",
                category="cost",
                title="Daily cost anomaly",
                priority=70,
                detail={"total_usd": total, "breakdown": breakdown},
            )
        return DailyCostReport(
            report_date=day,
            total_usd=round(total, 4),
            breakdown=breakdown,
            anomaly=anomaly,
            cognition_roi_hint=roi,
        )

    def markdown_report(self, report: DailyCostReport) -> str:
        lines = [
            f"# Daily cost report — {report.report_date}",
            "",
            f"**Total:** ${report.total_usd:.2f}",
            f"**Anomaly:** {'yes' if report.anomaly else 'no'}",
            f"**Cognition ROI:** {report.cognition_roi_hint}",
            "",
            "| Category | USD |",
            "|----------|-----|",
        ]
        for k, v in report.breakdown.items():
            lines.append(f"| {k} | ${v:.2f} |")
        return "\n".join(lines)
