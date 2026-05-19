from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bot.ops_observation.store import OpsObservationStore


def forecast_operational_pressure(
    *,
    pulse: dict[str, Any],
    events: list[dict[str, Any]],
    store: OpsObservationStore | None = None,
) -> dict[str, Any]:
    """Early warning from pulse history trends."""
    store = store or OpsObservationStore()
    lags: list[float] = []
    recoveries: list[int] = []
    anomalies: list[int] = []

    for path in sorted(store.pulses_dir.glob("*.jsonl"))[-7:]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            lags.append(float(p.get("event_loop_lag_max") or 0))
            recoveries.append(int(p.get("recovery_attempt_count") or 0))
            anomalies.append(len(p.get("anomalies") or []))

    cur_lag = float(pulse.get("event_loop_lag_max") or 0)
    cur_recovery = int(pulse.get("recovery_attempt_count") or 0)

    lag_trend = _trend(lags + [cur_lag])
    recovery_trend = _trend([float(x) for x in recoveries + [cur_recovery]])
    alert_accel = len(events) >= 8 and len(events) > max(1, len(lags))

    disk_velocity = "unknown"
    try:
        from bot.config import project_root

        var_ops = project_root() / "var" / "ops"
        if var_ops.is_dir():
            size = sum(f.stat().st_size for f in var_ops.rglob("*") if f.is_file())
            disk_velocity = "high" if size > 500_000_000 else "normal"
    except Exception:
        pass

    score = min(
        1.0,
        cur_lag * 0.4
        + cur_recovery * 0.06
        + (0.15 if lag_trend == "rising" else 0)
        + (0.2 if recovery_trend == "rising" else 0)
        + (0.1 if alert_accel else 0),
    )

    if score >= 0.75:
        level = "critical"
        summary = "Operational pressure likely to worsen within the hour"
        safe = "Reduce publish attempts and pause ingestion expansion"
    elif score >= 0.45:
        level = "elevated"
        summary = "Queue or lag trends suggest rising pressure"
        safe = "Observe /resilience_status for 15m before increasing publish rate"
    else:
        level = "normal"
        summary = "Near-term pressure within expected pilot bounds"
        safe = "Continue normal canary operations"

    return {
        "pressure_score": round(score, 3),
        "pressure_level": level,
        "summary": summary,
        "safe_next_step": safe,
        "lag_trend": lag_trend,
        "recovery_trend": recovery_trend,
        "alert_acceleration": alert_accel,
        "disk_growth": disk_velocity,
        "queue_growth": "unknown",
    }


def _trend(series: list[float]) -> str:
    if len(series) < 3:
        return "flat"
    recent = sum(series[-3:]) / 3
    prior = sum(series[:-3]) / max(1, len(series) - 3) if len(series) > 3 else recent
    if recent > prior * 1.2 + 0.05:
        return "rising"
    if recent < prior * 0.8 - 0.05:
        return "falling"
    return "flat"
