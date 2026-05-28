"""WARNING vs CRITICAL classification for execution-graph anomalies."""

from __future__ import annotations

from enum import Enum

# Structural violations — corrupt tick, block publish, exclude from burn-in metrics.
CRITICAL_ANOMALIES = frozenset(
    {
        "duplicate_summarize_path",
        "duplicate_publish_gate",
        "duplicate_finalize",
        "finalize_race_duplicate_attempt",
        "missing_summarize_path",
        "missing_finalize_begin",
        "publish_without_gate_allowed",
        "publish_consistency_violation",
        "ghost_publish_no_tick",
        "ghost_publish_outside_active_tick",
        "invalid_terminal_state",
        "terminal_outside_finalize",
    }
)

# Transient timing / ordering — log only unless they corrupt final state.
WARNING_ANOMALIES = frozenset(
    {
        "tick_overlap",
        "delayed_finalize",
        "late_publish_after_finalize",
        "publish_gate_after_finalize",
        "publish_gate_outside_active_tick",
        "ghost_publish_gate_no_tick",
    }
)


class AnomalySeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


def classify_anomaly(code: str) -> AnomalySeverity:
    base = code.split("=", 1)[0].strip()
    if base in CRITICAL_ANOMALIES:
        return AnomalySeverity.CRITICAL
    if base in WARNING_ANOMALIES:
        return AnomalySeverity.WARNING
    if base.startswith(("summarize_calls", "finalize_calls", "invalid_terminal")):
        return AnomalySeverity.CRITICAL
    return AnomalySeverity.WARNING


def partition_anomalies(codes: list[str]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    critical: list[str] = []
    for code in codes:
        if classify_anomaly(code) == AnomalySeverity.CRITICAL:
            critical.append(code)
        else:
            warnings.append(code)
    return warnings, critical
