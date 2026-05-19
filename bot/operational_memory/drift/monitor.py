from __future__ import annotations

from typing import Any

from bot.operational_memory.repository import OperationalMemoryRepository


_DOMAINS = (
    "audience",
    "source_quality",
    "engagement",
    "editorial",
    "latency",
    "anomaly",
)


class DriftMonitor:
    """Distinguish temporary anomaly vs systemic degradation."""

    def __init__(self, repository: OperationalMemoryRepository) -> None:
        self.repository = repository
        self._windows: dict[str, list[float]] = {d: [] for d in _DOMAINS}

    def evaluate(self, signals: dict[str, Any]) -> dict[str, dict[str, Any]]:
        metrics = {
            "audience": float(signals.get("audience_fatigue", signals.get("publish_fatigue", 0.2))),
            "source_quality": 1.0 - float(signals.get("source_health", 0.85)),
            "engagement": 1.0 - float(signals.get("engagement_score", 0.7)),
            "editorial": float(signals.get("editorial_drift", 0.1)),
            "latency": min(1.0, float(signals.get("cognition_latency_ms", 0)) / 10000.0),
            "anomaly": float(signals.get("noise_index", 0.3)),
        }
        results: dict[str, dict[str, Any]] = {}
        for domain, value in metrics.items():
            win = self._windows[domain]
            win.append(value)
            if len(win) > 24:
                win.pop(0)
            baseline = sum(win[:-1]) / max(len(win) - 1, 1) if len(win) > 1 else value
            deviation = abs(value - baseline)
            drift_score = min(1.0, deviation * 2.0)
            systemic = len(win) >= 6 and all(v > baseline + 0.05 for v in win[-3:])
            detail = {
                "current": value,
                "baseline": baseline,
                "deviation": deviation,
                "window_len": len(win),
            }
            self.repository.save_drift(
                domain=domain,
                drift_score=drift_score,
                systemic=systemic,
                detail=detail,
            )
            results[domain] = {
                "drift_score": drift_score,
                "systemic": systemic,
                "detail": detail,
            }
        return results

    def drift_report_html(self) -> str:
        rows = self.repository.latest_drift()
        lines = ["<b>Drift report</b>"]
        for r in rows:
            systemic = "SYSTEMIC" if r.get("systemic") else "transient"
            lines.append(
                f"{r['domain']}: {r['drift_score']:.0%} ({systemic})",
            )
        if len(lines) == 1:
            lines.append("No drift snapshots yet.")
        return "\n".join(lines)
