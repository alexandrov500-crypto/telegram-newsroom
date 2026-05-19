from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bot.ops_certification.certification.engine import CertificationResult
from bot.ops_certification.repository import OpsCertificationRepository
from bot.ops_certification.slo.engine import SloEngine


@dataclass
class ExecutiveReportGenerator:
    repository: OpsCertificationRepository

    def build_daily(
        self,
        *,
        certification: CertificationResult | None = None,
        slo_engine: SloEngine | None = None,
        stability_score: float = 1.0,
        ai_spend_usd: float = 0.0,
        publish_count: int = 0,
        incident_count: int = 0,
        trust_avg: float = 0.85,
    ) -> dict[str, Any]:
        slo_summary = slo_engine.error_budget_summary() if slo_engine else {}
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reliability_trend": stability_score,
            "operational_risk": len(slo_summary.get("slos", [])) - slo_summary.get(
                "violated_count",
                0,
            ),
            "ai_spend_usd": round(ai_spend_usd, 2),
            "publishes": publish_count,
            "incidents": incident_count,
            "trust_avg": trust_avg,
            "certification": certification.to_dict() if certification else {},
            "slo": slo_summary,
            "rollout_confidence": certification.score if certification else 0.0,
        }
        self.repository.save_executive_report(
            report_id=str(uuid.uuid4()),
            report_type="daily",
            summary=report,
        )
        return report

    def format_telegram(self, report: dict[str, Any]) -> str:
        lines = [
            "<b>📊 Executive ops report</b>",
            f"Reliability: {report.get('reliability_trend', 0):.0%}",
            f"AI spend: ${report.get('ai_spend_usd', 0):.2f}",
            f"Publishes: {report.get('publishes', 0)} · Incidents: {report.get('incidents', 0)}",
            f"Trust avg: {report.get('trust_avg', 0):.2f}",
        ]
        cert = report.get("certification", {})
        if cert:
            lines.append(f"Cert: {cert.get('state', 'n/a')} ({cert.get('score', 0):.0%})")
        slo = report.get("slo", {})
        if slo:
            lines.append(
                f"SLO violations: {slo.get('violated_count', 0)} · "
                f"burn {slo.get('critical_burn', 0):.2f}",
            )
        return "\n".join(lines)
