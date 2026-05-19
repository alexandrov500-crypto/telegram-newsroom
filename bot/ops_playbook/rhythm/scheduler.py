from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ops_playbook.repository import OpsPlaybookRepository


@dataclass
class OperationsRhythmScheduler:
    """Daily / weekly / monthly operational routines."""

    repository: OpsPlaybookRepository
    _tick: int = 0

    def tick(self, signals: dict[str, Any]) -> dict[str, Any]:
        self._tick += 1
        out: dict[str, Any] = {}
        if self._tick % 24 == 0:
            out["daily"] = self._daily(signals)
        if self._tick % 168 == 0:
            out["weekly"] = self._weekly(signals)
        if self._tick % 720 == 0:
            out["monthly"] = self._monthly(signals)
        return out

    def _daily(self, sig: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "executive_summary": self.executive_summary(sig),
            "risk_forecast": round(float(sig.get("risk_forecast", 0.3)), 3),
            "maturity": sig.get("maturity_overall", 0),
            "quality_drift": sig.get("quality_drift", "stable"),
            "source_degradation": sig.get("source_degradation", []),
            "budget_forecast": sig.get("budget_forecast", {}),
        }
        self.repository.log_rhythm("daily", payload)
        return payload

    def _weekly(self, sig: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "optimization_proposals": sig.get("pending_optimizations", 0),
            "maintenance": sig.get("maintenance_pending", 0),
            "scaling_readiness": 1.0 - float(sig.get("scaling_risk", 0.2)),
            "governance_trend": sig.get("trust_trend", "stable"),
        }
        self.repository.log_rhythm("weekly", payload)
        return payload

    def _monthly(self, sig: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "maturity_evolution": sig.get("maturity_overall", 0),
            "incident_recurrence": sig.get("incident_recurrence", []),
            "sustainability": sig.get("sustainability", 0.8),
        }
        self.repository.log_rhythm("monthly", payload)
        return payload

    def executive_summary(self, sig: dict[str, Any]) -> str:
        return (
            f"Queue {sig.get('queue_depth', 0)} · "
            f"rollout {sig.get('rollout_stage', '?')} · "
            f"GA {sig.get('go_live_confidence', 0):.2f}"
        )

    def daily_html(self, sig: dict[str, Any]) -> str:
        p = self._daily(sig)
        return (
            "<b>Daily ops rhythm</b>\n"
            f"{p['executive_summary']}\n"
            f"Risk: {p['risk_forecast']:.2f} · Maturity: {p['maturity']:.2f}\n"
            f"Quality drift: {p['quality_drift']}"
        )
