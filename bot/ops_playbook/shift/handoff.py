from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository


@dataclass
class ShiftHandoffEngine:
    repository: OpsPlaybookRepository

    def build_report(self, signals: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        if float(signals.get("operator_attention", 1)) > 0.75:
            warnings.append("high_operator_attention_risk")
        if float(signals.get("scaling_risk", 0)) > 0.5:
            warnings.append("scaling_pressure")
        if signals.get("open_incidents", 0) > 0:
            warnings.append("active_incidents")
        if float(signals.get("ecosystem_risk", 0)) > 0.5:
            warnings.append("ecosystem_risk_elevated")

        return {
            "rollout_stage": signals.get("rollout_stage", "INTERNAL_SHADOW"),
            "active_incidents": signals.get("open_incidents", 0),
            "degraded_subsystems": signals.get("degraded_subsystems", []),
            "risk_forecast": round(float(signals.get("risk_forecast", 0.3)), 3),
            "publish_pressure": round(float(signals.get("publish_pressure", 0)), 2),
            "audience_health": round(float(signals.get("audience_health", 0.85)), 3),
            "trust_trajectory": signals.get("trust_trend", "stable"),
            "operator_attention_risk": round(float(signals.get("operator_attention", 0.5)), 3),
            "pending_approvals": int(signals.get("pending_approvals", 0)),
            "pending_optimizations": int(signals.get("pending_optimizations", 0)),
            "rollback_ready": signals.get("rollback_ready", True),
            "warnings": warnings,
        }

    def handoff_html(self, report: dict[str, Any], *, owner: str | None) -> str:
        lines = [
            "<b>Shift handoff</b>",
            f"Owner: <code>{owner or 'unassigned'}</code>",
            f"Rollout: <code>{report['rollout_stage']}</code>",
            f"Incidents: {report['active_incidents']}",
            f"Risk forecast: {report['risk_forecast']:.2f}",
            f"Publish pressure: {report['publish_pressure']:.2f}",
            f"Audience: {report['audience_health']:.2f} · trust {report['trust_trajectory']}",
            f"Operator load: {report['operator_attention_risk']:.2f}",
            f"Pending approvals: {report['pending_approvals']}",
            f"Optimizations: {report['pending_optimizations']}",
            f"Rollback ready: {'yes' if report['rollback_ready'] else 'no'}",
        ]
        degraded = report.get("degraded_subsystems") or []
        if degraded:
            lines.append("Degraded: " + ", ".join(str(d) for d in degraded[:5]))
        warns = report.get("warnings") or []
        if warns:
            lines.append("<b>Unresolved warnings</b>")
            for w in warns[:6]:
                lines.append(f"• {w}")
        return "\n".join(lines)

    def take_shift(self, operator_id: str, signals: dict[str, Any]) -> str:
        report = self.build_report(signals)
        self.repository.save_shift(
            owner_operator_id=operator_id,
            handoff=report,
            warnings=report.get("warnings", []),
        )
        self.repository.record_shift_ack(operator_id, "take_shift", {"report": report})
        return self.handoff_html(report, owner=operator_id)

    def acknowledge(self, operator_id: str) -> str:
        shift = self.repository.get_shift() or {}
        self.repository.record_shift_ack(
            operator_id,
            "handoff_ack",
            {"warnings_cleared": True},
        )
        self.repository.save_shift(
            owner_operator_id=shift.get("owner_operator_id"),
            handoff=json_loads_safe(shift.get("handoff_json")),
            warnings=[],
        )
        return f"Handoff acknowledged by <code>{operator_id}</code>."


def json_loads_safe(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
