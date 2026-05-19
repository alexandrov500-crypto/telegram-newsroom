from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository
from bot.ops_playbook.settings import OpsPlaybookSettings


@dataclass
class LaunchPeriodProtections:
    """First-30-days elevated protections — auto-relax after window."""

    repository: OpsPlaybookRepository
    settings: OpsPlaybookSettings

    def ensure_initialized(self, production_start_at: str) -> None:
        self.repository.init_launch_period(
            production_start_at=production_start_at,
            launch_risk=0.5,
        )

    def days_since_launch(self) -> int:
        row = self.repository.get_launch_period()
        if not row:
            return 0
        try:
            start = datetime.fromisoformat(row["production_start_at"].replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - start
            return max(0, delta.days)
        except ValueError:
            return 0

    def active(self) -> bool:
        row = self.repository.get_launch_period()
        if not row:
            return False
        if not row.get("protections_active"):
            return False
        return self.days_since_launch() < self.settings.launch_period_days

    def launch_risk_score(self, signals: dict[str, Any]) -> float:
        base = float(signals.get("risk_forecast", 0.3))
        if not self.active():
            return base
        sensitivity = 1.25 if self.settings.launch_period_elevated_sensitivity else 1.0
        risk = min(1.0, base * sensitivity)
        if float(signals.get("quality_avg", 0.8)) < 0.75:
            risk = min(1.0, risk + 0.15)
        if signals.get("open_incidents", 0) > 0:
            risk = min(1.0, risk + 0.1)
        self.repository.update_launch_risk(
            risk,
            protections_active=self.active(),
        )
        return risk

    def thresholds(self) -> dict[str, Any]:
        if not self.active():
            return {
                "rollback_threshold": 0.15,
                "trust_gate": 0.7,
                "anomaly_multiplier": 1.0,
            }
        return {
            "rollback_threshold": 0.08,
            "trust_gate": 0.78,
            "anomaly_multiplier": 1.35,
            "executive_reporting": "enhanced",
            "telemetry_retention": "extended",
        }

    def status_html(self) -> str:
        days = self.days_since_launch()
        active = self.active()
        row = self.repository.get_launch_period() or {}
        return (
            f"<b>Launch period</b> day {days}/{self.settings.launch_period_days}\n"
            f"Protections: {'active' if active else 'relaxed'}\n"
            f"Launch risk: {row.get('launch_risk_score', 0):.2f}"
        )
