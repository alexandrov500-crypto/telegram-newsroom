from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class OpsAdvisor:
    """Automated maintenance hints, checklists, risk forecasting."""

    maintenance_hour_utc: int = 4

    def in_maintenance_window(self) -> bool:
        return datetime.now(timezone.utc).hour == self.maintenance_hour_utc

    def advise(
        self,
        *,
        queue_depth: int = 0,
        slo_violations: int = 0,
        budget_anomaly: bool = False,
        scaling_risk: float = 0.0,
        failure_issues: list[dict[str, Any]] | None = None,
    ) -> str:
        lines = ["<b>Ops advisor</b>"]
        if self.in_maintenance_window():
            lines.append("🛠 Maintenance window active — prefer read-only ops")
        if slo_violations > 0:
            lines.append(f"⛔ {slo_violations} SLO violations → /slo_live")
        if budget_anomaly:
            lines.append("💰 Budget anomaly → enable cost saving mode")
        if scaling_risk > 0.6:
            lines.append("📈 Scaling risk high → /publish_load · add workers")
        if queue_depth > 400:
            lines.append("📬 Queue pressure → pause nonessential ingest")
        for issue in (failure_issues or [])[:3]:
            lines.append(f"• {issue.get('id')}: {issue.get('remediation', '/system_risk')[:40]}")
        if len(lines) == 1:
            lines.append("✅ No urgent advisories")
        lines.append("\n<b>Checklist</b>")
        lines.append("□ /ga_status □ /launch_dashboard □ /config_status")
        return "\n".join(lines)

    def maintenance_status(self) -> str:
        now = datetime.now(timezone.utc)
        in_win = self.in_maintenance_window()
        return (
            f"<b>Maintenance</b>\n"
            f"Window: {self.maintenance_hour_utc}:00 UTC\n"
            f"Now: {now.strftime('%H:%M')}Z · active: {'yes' if in_win else 'no'}"
        )
