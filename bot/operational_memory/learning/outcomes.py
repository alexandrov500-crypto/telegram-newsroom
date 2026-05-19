from __future__ import annotations

from typing import Any

from bot.operational_memory.repository import OperationalMemoryRepository


class OutcomeLearner:
    """Track recovery patterns from closed incidents."""

    def __init__(self, repository: OperationalMemoryRepository) -> None:
        self.repository = repository

    def recovery_patterns(self) -> list[dict[str, Any]]:
        incidents = self.repository.list_incidents(limit=50)
        by_type: dict[str, list[float]] = {}
        for inc in incidents:
            if inc.get("recovery_duration_sec") is None:
                continue
            t = inc["incident_type"]
            by_type.setdefault(t, []).append(float(inc["recovery_duration_sec"]))
        patterns = []
        for t, durations in by_type.items():
            patterns.append(
                {
                    "incident_type": t,
                    "count": len(durations),
                    "avg_recovery_sec": sum(durations) / len(durations),
                    "min_recovery_sec": min(durations),
                    "max_recovery_sec": max(durations),
                },
            )
        return sorted(patterns, key=lambda x: -x["count"])

    def recovery_patterns_html(self) -> str:
        patterns = self.recovery_patterns()
        lines = ["<b>Recovery patterns</b> (historical)"]
        for p in patterns[:8]:
            lines.append(
                f"{p['incident_type']}: n={p['count']} avg {p['avg_recovery_sec']:.0f}s",
            )
        if len(lines) == 1:
            lines.append("No closed incidents with recovery data yet.")
        return "\n".join(lines)
