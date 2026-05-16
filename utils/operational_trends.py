"""Deterministic operational trend analysis (no ML; read-only)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

TrendDirection = Literal["stable", "rising", "falling", "unknown"]

TREND_SAMPLE_SCHEMA = 1


@dataclass
class TrendSample:
    """Point-in-time operational signals for trend analysis."""

    captured_at: str
    wal_bytes: int = 0
    retry_burst_window: int = 0
    evidence_dir_bytes: int = 0
    runtime_dir_bytes: int = 0
    queue_pending: int = 0
    dlq_counter_total: int = 0
    scheduler_overlap_total: int = 0
    scheduler_max_lag_sec: float = 0.0
    drift_finding_count: int = 0
    restore_duration_estimate_sec: float = 0.0
    redis_reconnect_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TREND_SAMPLE_SCHEMA,
            "captured_at": self.captured_at,
            "wal_bytes": self.wal_bytes,
            "retry_burst_window": self.retry_burst_window,
            "evidence_dir_bytes": self.evidence_dir_bytes,
            "runtime_dir_bytes": self.runtime_dir_bytes,
            "queue_pending": self.queue_pending,
            "dlq_counter_total": self.dlq_counter_total,
            "scheduler_overlap_total": self.scheduler_overlap_total,
            "scheduler_max_lag_sec": self.scheduler_max_lag_sec,
            "drift_finding_count": self.drift_finding_count,
            "restore_duration_estimate_sec": self.restore_duration_estimate_sec,
            "redis_reconnect_count": self.redis_reconnect_count,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrendSample:
        return cls(
            captured_at=str(data.get("captured_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            wal_bytes=int(data.get("wal_bytes") or 0),
            retry_burst_window=int(data.get("retry_burst_window") or 0),
            evidence_dir_bytes=int(data.get("evidence_dir_bytes") or 0),
            runtime_dir_bytes=int(data.get("runtime_dir_bytes") or 0),
            queue_pending=int(data.get("queue_pending") or 0),
            dlq_counter_total=int(data.get("dlq_counter_total") or 0),
            scheduler_overlap_total=int(data.get("scheduler_overlap_total") or 0),
            scheduler_max_lag_sec=float(data.get("scheduler_max_lag_sec") or 0.0),
            drift_finding_count=int(data.get("drift_finding_count") or 0),
            restore_duration_estimate_sec=float(data.get("restore_duration_estimate_sec") or 0.0),
            redis_reconnect_count=int(data.get("redis_reconnect_count") or 0),
            extra=dict(data.get("extra") or {}),
        )


def _dlq_total_from_counters(counters: dict[str, Any]) -> int:
    total = 0
    for k, v in counters.items():
        if "dlq" in str(k).lower():
            try:
                total += int(v)
            except (TypeError, ValueError):
                continue
    return total


def sample_from_runtime_signals(sig: dict[str, Any], *, scheduler_snap: dict[str, Any] | None = None) -> TrendSample:
    counters = dict(sig.get("counters") or {})
    sched = scheduler_snap or {}
    jobs = sched.get("jobs") or {}
    max_lag = 0.0
    for info in jobs.values():
        if isinstance(info, dict):
            lag = info.get("max_lag_sec")
            if lag is not None:
                max_lag = max(max_lag, float(lag))
    rt_bytes = int(sig.get("runtime_dir_bytes") or 0)
    file_est = max(1, rt_bytes // 4096) if rt_bytes else 12
    restore_est = round(max(0.01, (rt_bytes / (1024 * 1024)) * 0.02 + file_est * 0.001), 4)
    redis_rc = 0
    try:
        from utils.redis_transport_metrics import snapshot as rtm

        m = rtm()
        redis_rc = int(m.get("reconnect_count") or m.get("errors") or 0)
    except Exception:
        pass
    return TrendSample(
        captured_at=str(sig.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        wal_bytes=int(sig.get("wal_bytes") or 0),
        retry_burst_window=int(sig.get("retry_burst_window") or 0),
        evidence_dir_bytes=int(sig.get("evidence_dir_bytes") or 0),
        runtime_dir_bytes=rt_bytes,
        queue_pending=int(sig.get("queue_pending") or 0),
        dlq_counter_total=_dlq_total_from_counters(counters),
        scheduler_overlap_total=int(sched.get("overlap_total") or 0),
        scheduler_max_lag_sec=max_lag,
        drift_finding_count=int(sig.get("drift_finding_count") or 0),
        restore_duration_estimate_sec=restore_est,
        redis_reconnect_count=redis_rc,
    )


def load_history_dir(history_dir: Path) -> list[TrendSample]:
    if not history_dir.is_dir():
        return []
    samples: list[TrendSample] = []
    for path in sorted(history_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                samples.extend(TrendSample.from_dict(x) for x in data if isinstance(x, dict))
            elif isinstance(data, dict):
                samples.append(TrendSample.from_dict(data))
        except (OSError, json.JSONDecodeError):
            continue
    samples.sort(key=lambda s: s.captured_at)
    return samples[-64:]


def rolling_baseline(samples: list[TrendSample], *, window: int = 8) -> dict[str, float]:
    if not samples:
        return {}
    windowed = samples[-window:]
    n = len(windowed)

    def avg(attr: str) -> float:
        vals = [float(getattr(s, attr)) for s in windowed]
        return round(sum(vals) / n, 4) if n else 0.0

    return {
        "sample_count": float(n),
        "wal_bytes": avg("wal_bytes"),
        "retry_burst_window": avg("retry_burst_window"),
        "evidence_dir_bytes": avg("evidence_dir_bytes"),
        "dlq_counter_total": avg("dlq_counter_total"),
        "scheduler_max_lag_sec": avg("scheduler_max_lag_sec"),
        "queue_pending": avg("queue_pending"),
        "restore_duration_estimate_sec": avg("restore_duration_estimate_sec"),
        "drift_finding_count": avg("drift_finding_count"),
    }


def _parse_ts(iso: str) -> float:
    try:
        from datetime import datetime

        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time()


def _per_day_rate(samples: list[TrendSample], attr: str) -> float:
    if len(samples) < 2:
        return 0.0
    first, last = samples[0], samples[-1]
    dt_days = max(1 / 24, (_parse_ts(last.captured_at) - _parse_ts(first.captured_at)) / 86400.0)
    delta = float(getattr(last, attr)) - float(getattr(first, attr))
    return round(delta / dt_days, 4)


def _direction(rate: float, *, eps: float = 0.01) -> TrendDirection:
    if abs(rate) < eps:
        return "stable"
    return "rising" if rate > 0 else "falling"


def analyze_trends(samples: list[TrendSample]) -> dict[str, Any]:
    """Trend analysis with rolling baselines, anomalies, and maintenance hints."""
    if not samples:
        return {
            "schema_version": 1,
            "sample_count": 0,
            "baseline": {},
            "trends": {},
            "anomalies": [],
            "maintenance_hints": ["Collect trend history: save TrendSample JSON under var/ops_history/"],
        }

    baseline = rolling_baseline(samples)
    current = samples[-1]
    trends: dict[str, Any] = {}
    metrics = (
        ("wal_bytes", "wal_growth"),
        ("retry_burst_window", "retry_frequency"),
        ("dlq_counter_total", "dlq_growth"),
        ("scheduler_max_lag_sec", "scheduler_lag"),
        ("evidence_dir_bytes", "evidence_growth"),
        ("restore_duration_estimate_sec", "restore_duration"),
        ("queue_pending", "queue_pressure"),
        ("drift_finding_count", "drift_frequency"),
    )
    anomalies: list[dict[str, Any]] = []
    hints: list[str] = []

    for attr, label in metrics:
        rate = _per_day_rate(samples, attr)
        cur = float(getattr(current, attr))
        base = float(baseline.get(attr, 0.0))
        direction = _direction(rate)
        trends[label] = {
            "direction": direction,
            "per_day_delta": rate,
            "current": cur,
            "rolling_mean": base,
        }
        if base > 0 and cur > base * 1.5 and cur - base > 1:
            anomalies.append(
                {
                    "metric": label,
                    "severity": "MEDIUM",
                    "message": f"{label} above rolling baseline ({cur} vs mean {base})",
                }
            )

    if trends.get("wal_growth", {}).get("direction") == "rising" and current.wal_bytes > 64_000_000:
        hints.append("WAL trending up — plan quiesced checkpoint within 7 days")
    if trends.get("evidence_growth", {}).get("direction") == "rising":
        hints.append("Evidence directory growing — schedule retention prune")
    if current.retry_burst_window >= 20:
        hints.append("Retry burst elevated — investigate upstream before scaling workers")
    if current.scheduler_overlap_total > 0:
        hints.append("Scheduler overlap observed — review job intervals")
    if trends.get("restore_duration", {}).get("current", 0) > 30:
        hints.append("Restore duration estimate high — test recovery drill in maintenance window")

    return {
        "schema_version": 1,
        "sample_count": len(samples),
        "baseline": baseline,
        "trends": trends,
        "anomalies": anomalies[:8],
        "maintenance_hints": hints[:10],
        "confidence": "low" if len(samples) < 3 else ("medium" if len(samples) < 8 else "high"),
    }
