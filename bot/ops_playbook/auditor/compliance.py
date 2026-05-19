from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository


@dataclass
class OperationsAuditor:
    repository: OpsPlaybookRepository

    def run_audit(self, signals: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
        findings: list[dict[str, Any]] = []

        if signals.get("rollout_stage") not in (
            "INTERNAL_SHADOW",
            "LIMITED_CHANNELS",
            "LOW_FREQUENCY_PUBLIC",
            "NORMAL_PRODUCTION",
        ):
            findings.append(
                {
                    "id": "rollout_compliance",
                    "severity": "high",
                    "detail": "Unknown rollout stage",
                },
            )

        if float(signals.get("quality_avg", 1)) < 0.65:
            findings.append(
                {
                    "id": "quality_compliance",
                    "severity": "medium",
                    "detail": "Quality below policy floor",
                },
            )

        if not signals.get("rollback_ready", True):
            findings.append(
                {
                    "id": "rollback_readiness",
                    "severity": "high",
                    "detail": "Rollback path not verified",
                },
            )

        if float(signals.get("operator_attention", 0)) > 0.85:
            findings.append(
                {
                    "id": "operator_load",
                    "severity": "low",
                    "detail": "Operator attention risk elevated",
                },
            )

        if not signals.get("certified", False) and signals.get("is_production"):
            findings.append(
                {
                    "id": "certification",
                    "severity": "medium",
                    "detail": "Not certified for production",
                },
            )

        if float(signals.get("slo_compliance", 1)) < 0.95:
            findings.append(
                {
                    "id": "slo_discipline",
                    "severity": "high",
                    "detail": "SLO compliance below threshold",
                },
            )

        score = max(0.0, 1.0 - len(findings) * 0.12)
        self.repository.save_audit(findings=findings, compliance_score=score)
        return score, findings

    def audit_html(self, signals: dict[str, Any]) -> str:
        score, findings = self.run_audit(signals)
        lines = [f"<b>Ops audit</b> compliance {score:.0%}"]
        for f in findings[:8]:
            lines.append(f"• [{f['severity']}] {f['id']}: {f['detail']}")
        if not findings:
            lines.append("No findings — compliant")
        return "\n".join(lines)

    def compliance_status_html(self) -> str:
        last = self.repository.latest_audit()
        if not last:
            return "<b>Compliance</b>\nRun /ops_audit first."
        drift = [f for f in last["findings"] if f.get("severity") in ("high", "medium")]
        return (
            f"<b>Compliance status</b> {last['compliance_score']:.0%}\n"
            f"Findings: {len(last['findings'])} · drift: {len(drift)}\n"
            f"Updated: {last.get('created_at', '?')[:19]}"
        )
