from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _baseline_metrics(baseline: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    lag = baseline.get("event_loop_lag_max") or {}
    if isinstance(lag, dict):
        if lag.get("max") is not None:
            out["event_loop_lag_max"] = float(lag["max"])
    elif isinstance(lag, (int, float)):
        out["event_loop_lag_max"] = float(lag)
    if baseline.get("publish_latency_sec") is not None:
        out["publish_latency_sec"] = float(baseline["publish_latency_sec"])
    if baseline.get("recovery_attempt_count") is not None:
        out["recovery_attempt_count"] = float(baseline["recovery_attempt_count"])
    trust = baseline.get("trust_score")
    if trust is not None:
        out["trust_score"] = float(trust)
    return out


def detect_operational_drift(
    current: dict[str, Any],
    *,
    baseline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compare current pulse/snapshot metrics against locked Day-0 baseline."""
    from bot.ops_forensics.repository import ForensicsRepository

    if baseline is None:
        baseline = ForensicsRepository().get_baseline()
    if not baseline:
        try:
            from bot.ops_observation.store import OpsObservationStore

            baseline = OpsObservationStore().load_baseline()
        except Exception:
            baseline = {}

    base = _baseline_metrics(baseline)
    if not base:
        return []

    warnings: list[dict[str, Any]] = []
    lag_now = float(current.get("event_loop_lag_max") or 0.0)
    lag_base = base.get("event_loop_lag_max", 0.05)
    lag_mult = float(os.getenv("DRIFT_LAG_MULTIPLIER", "4"))
    if lag_base > 0 and lag_now > max(lag_base * lag_mult, 0.5):
        warnings.append(
            {
                "metric": "event_loop_lag_max",
                "baseline": lag_base,
                "current": lag_now,
                "severity": "warning",
            },
        )

    recovery_now = float(current.get("recovery_attempt_count") or 0)
    recovery_base = base.get("recovery_attempt_count", 0)
    if recovery_now > recovery_base + float(os.getenv("DRIFT_RECOVERY_DELTA", "5")):
        warnings.append(
            {
                "metric": "recovery_attempt_count",
                "baseline": recovery_base,
                "current": recovery_now,
                "severity": "warning",
            },
        )

    pub_lat = current.get("publish_latency_sec")
    pub_base = base.get("publish_latency_sec")
    if pub_lat is not None and pub_base is not None and pub_base > 0:
        if float(pub_lat) > float(pub_base) * float(os.getenv("DRIFT_PUBLISH_LATENCY_MULT", "2.5")):
            warnings.append(
                {
                    "metric": "publish_latency_sec",
                    "baseline": pub_base,
                    "current": float(pub_lat),
                    "severity": "warning",
                },
            )

    trust_now = current.get("trust_score")
    trust_base = base.get("trust_score")
    if trust_now is not None and trust_base is not None:
        if float(trust_now) < float(trust_base) - float(os.getenv("DRIFT_TRUST_DROP", "0.15")):
            warnings.append(
                {
                    "metric": "trust_score",
                    "baseline": trust_base,
                    "current": float(trust_now),
                    "severity": "warning",
                },
            )

    for w in warnings:
        logger.warning(
            "event=operational_drift_detected metric=%s baseline=%s current=%s",
            w["metric"],
            w["baseline"],
            w["current"],
        )
        try:
            from bot.ops_forensics.hooks import record_timeline

            record_timeline(
                "operational_drift_detected",
                severity=str(w.get("severity", "warning")),
                details=w,
            )
        except Exception:
            pass

    return warnings
