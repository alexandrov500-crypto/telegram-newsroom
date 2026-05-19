from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperationalReadinessScore:
    overall: float
    trend: str
    components: dict[str, float]
    blockers: list[str]

    def summary_text(self) -> str:
        lines = [
            "<b>Operational readiness</b>",
            f"Overall: <b>{self.overall:.2f}</b> ({self.trend})",
            "",
            f"Ingestion: {self.components.get('ingestion', 0):.2f}",
            f"Telegram: {self.components.get('telegram', 0):.2f}",
            f"Cognition: {self.components.get('cognition', 0):.2f}",
            f"Epistemic: {self.components.get('epistemic', 0):.2f}",
            f"Operator UX: {self.components.get('operator', 0):.2f}",
            f"Replay: {self.components.get('replay', 0):.2f}",
            f"Federation: {self.components.get('federation', 0):.2f}",
            f"Runtime: {self.components.get('runtime', 0):.2f}",
        ]
        if self.blockers:
            lines.append("\n<b>Blockers</b>")
            for b in self.blockers[:5]:
                lines.append(f"• {b}")
        return "\n".join(lines)


def _fatigue_numeric(raw: Any) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    label = str(raw or "moderate").lower()
    return {"low": 0.2, "normal": 0.35, "moderate": 0.5, "elevated": 0.72, "high": 0.9}.get(
        label, 0.5,
    )


def compute_operational_readiness(*, signals: dict[str, Any], ops_report: dict[str, Any]) -> OperationalReadinessScore:
    ingestion = max(0.0, min(1.0, 1.0 - float(signals.get("feed_quarantine_rate", 0))))
    telegram = max(
        0.0,
        min(1.0, 1.0 - float(signals.get("telegram_failure_rate_6h", 0))),
    )
    cognition = float(signals.get("mesh_health", 1.0))
    epistemic = float(signals.get("epistemic_stability", 1.0))
    operator = max(0.0, min(1.0, 1.0 - _fatigue_numeric(ops_report.get("operator_fatigue", 0))))
    replay = max(0.0, min(1.0, 1.0 - float(ops_report.get("replay_divergence", 0)) * 2))
    federation = float(signals.get("mesh_health", 1.0))
    runtime = float(ops_report.get("long_run_health", 0.8))
    components = {
        "ingestion": round(ingestion, 3),
        "telegram": round(telegram, 3),
        "cognition": round(cognition, 3),
        "epistemic": round(epistemic, 3),
        "operator": round(operator, 3),
        "replay": round(replay, 3),
        "federation": round(federation, 3),
        "runtime": round(runtime, 3),
    }
    overall = round(
        0.15 * ingestion
        + 0.12 * telegram
        + 0.12 * cognition
        + 0.18 * epistemic
        + 0.13 * operator
        + 0.15 * replay
        + 0.08 * federation
        + 0.07 * runtime,
        3,
    )
    blockers: list[str] = []
    if ingestion < 0.5:
        blockers.append("feed reliability degraded")
    if telegram < 0.7:
        blockers.append("telegram delivery failures elevated")
    if epistemic < 0.55:
        blockers.append("epistemic stability below threshold")
    if replay < 0.5:
        blockers.append("replay sustainability at risk")
    if ops_report.get("stalled_loops"):
        blockers.append(f"stalled loops: {ops_report['stalled_loops']}")
    trend = "healthy" if overall >= 0.82 else "degrading" if overall < 0.55 else "stable"
    return OperationalReadinessScore(overall=overall, trend=trend, components=components, blockers=blockers)
