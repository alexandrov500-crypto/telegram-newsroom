from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.live_deploy.repository import LiveDeployRepository


@dataclass
class ExecutiveGoLiveReport:
    repository: LiveDeployRepository

    def build(self, report_type: str, signals: dict[str, Any]) -> str:
        title = {
            "startup": "Launch startup",
            "first_publication": "First publication",
            "first_hour": "First hour",
            "24h": "24 hour",
            "72h": "72 hour",
        }.get(report_type, report_type)

        risks = signals.get("active_risks") or []
        risk_lines = "\n".join(f"• {r}" for r in risks[:5]) if risks else "• none flagged"

        return (
            f"<b>Executive go-live — {title}</b>\n\n"
            f"<b>Rollout</b> <code>{signals.get('rollout_stage', '?')}</code>\n"
            f"<b>GA readiness</b> {signals.get('ga_ready_score', 0):.2f}\n"
            f"<b>Publish health</b> {signals.get('publish_health', 0):.2f}\n"
            f"<b>Audience</b> {signals.get('audience_health', 0):.2f}\n"
            f"<b>Operator readiness</b> {signals.get('operator_readiness', 0):.2f}\n"
            f"<b>Rollback ready</b> {'yes' if signals.get('rollback_ready') else 'no'}\n"
            f"<b>Quality confidence</b> {signals.get('quality_confidence', 0):.2f}\n"
            f"<b>Trust</b> {signals.get('trust_trajectory', 'stable')}\n"
            f"<b>Scaling pressure</b> {signals.get('scaling_pressure', 0):.2f}\n"
            f"<b>Certification</b> {signals.get('certification_state', '?')}\n\n"
            f"<b>Active risks</b>\n{risk_lines}"
        )

    def should_send(self, report_key: str) -> bool:
        return not self.repository.report_sent(report_key)

    def mark_sent(self, report_key: str) -> None:
        self.repository.mark_report_sent(report_key)
