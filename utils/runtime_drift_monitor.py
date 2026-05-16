"""Runtime drift detection (opt-in; inspection-friendly JSON reports)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

DriftLevel = Literal["OK", "WARNING", "FAIL"]

DRIFT_REPORT_SCHEMA_VERSION = 1


@dataclass
class DriftBaseline:
    """Captured reference signals for comparison."""

    captured_at: str
    config_fingerprint: dict[str, str]
    counters: dict[str, int]
    queue_pending: int = 0
    retry_burst_window: int = 0
    wal_bytes: int = 0
    runtime_dir_bytes: int = 0
    evidence_dir_bytes: int = 0
    rss_bytes: int | None = None
    asyncio_tasks: int = 0
    degraded_mode_events: int = 0


@dataclass
class DriftFinding:
    category: str
    level: DriftLevel
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


def config_fingerprint(settings: Any) -> dict[str, str]:
    keys = (
        "redis_enabled",
        "worker_retry_safe",
        "publish_lock_strict",
        "deployment_profile",
        "pipeline_interval_minutes",
        "runtime_drift_monitor_enabled",
        "scheduler_diagnostics_enabled",
        "security_redaction_enabled",
    )
    out: dict[str, str] = {}
    for k in keys:
        if hasattr(settings, k):
            out[k] = str(getattr(settings, k))
    out["database_url_hint"] = (
        "sqlite" if "sqlite" in str(getattr(settings, "database_url", "")) else "other"
    )
    return out


def _sqlite_wal_bytes(database_url: str) -> int:
    url = str(database_url or "")
    if "sqlite" not in url.lower():
        return 0
    db = url.split("///")[-1].split("?")[0]
    if not db or db == ":memory:":
        return 0
    p = Path(db)
    wal = Path(f"{p}-wal")
    return int(wal.stat().st_size) if wal.is_file() else 0


def _dir_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except OSError:
                continue
    return total


def collect_runtime_signals(settings: Any, *, output_dir: Path | None = None) -> dict[str, Any]:
    from utils.diagnostics import rss_bytes_best_effort
    from utils.metrics import export_snapshot

    try:
        import asyncio

        tasks = len(asyncio.all_tasks()) if asyncio.get_event_loop().is_running() else 0
    except Exception:
        tasks = 0

    snap = export_snapshot()
    counters = dict(snap.get("counters") or {})

    rt_dir = Path(str(getattr(settings, "runtime_state_dir", "var/runtime"))).expanduser()
    od = output_dir or Path(os.environ.get("OUTPUT_DIR", "runtime_ops_output")).expanduser()

    retry_burst = 0
    try:
        import asyncio
        from workers import state as worker_state

        async def _burst() -> int:
            d = await worker_state.collect_runtime_diag(settings)
            return int(d.get("retry_burst_window") or 0)

        try:
            asyncio.get_running_loop()
            # Caller should pass retry_burst via metrics in async contexts; avoid nested loop.
        except RuntimeError:
            retry_burst = asyncio.run(_burst())
        else:
            counters_retry = int(counters.get("openai_retries") or 0)
            retry_burst = counters_retry
    except Exception:
        pass

    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": config_fingerprint(settings),
        "counters": counters,
        "retry_burst_window": retry_burst,
        "wal_bytes": _sqlite_wal_bytes(str(getattr(settings, "database_url", ""))),
        "runtime_dir_bytes": _dir_bytes(rt_dir),
        "evidence_dir_bytes": _dir_bytes(od),
        "rss_bytes": rss_bytes_best_effort(),
        "asyncio_tasks": tasks,
    }


def capture_baseline(settings: Any, *, output_dir: Path | None = None) -> DriftBaseline:
    sig = collect_runtime_signals(settings, output_dir=output_dir)
    return DriftBaseline(
        captured_at=str(sig["ts"]),
        config_fingerprint=dict(sig["config"]),
        counters={k: int(v) for k, v in sig["counters"].items()},
        retry_burst_window=int(sig["retry_burst_window"]),
        wal_bytes=int(sig["wal_bytes"]),
        runtime_dir_bytes=int(sig["runtime_dir_bytes"]),
        evidence_dir_bytes=int(sig["evidence_dir_bytes"]),
        rss_bytes=sig.get("rss_bytes"),
        asyncio_tasks=int(sig["asyncio_tasks"]),
    )


def _pct_growth(before: int, after: int) -> float:
    if before <= 0:
        return 100.0 if after > 0 else 0.0
    return round(100.0 * (after - before) / before, 2)


def compare_baselines(
    baseline: DriftBaseline,
    current: DriftBaseline,
    *,
    wal_warn_pct: float = 50.0,
    evidence_warn_pct: float = 80.0,
    retry_burst_warn: int = 30,
) -> list[DriftFinding]:
    findings: list[DriftFinding] = []

    if baseline.config_fingerprint != current.config_fingerprint:
        findings.append(
            DriftFinding(
                "config_drift",
                "WARNING",
                "Configuration fingerprint changed since baseline",
                {"before": baseline.config_fingerprint, "after": current.config_fingerprint},
            )
        )

    wal_g = _pct_growth(baseline.wal_bytes, current.wal_bytes)
    if wal_g >= wal_warn_pct and current.wal_bytes > 1_048_576:
        findings.append(
            DriftFinding(
                "wal_growth",
                "WARNING",
                f"SQLite WAL grew {wal_g}% since baseline",
                {"before": baseline.wal_bytes, "after": current.wal_bytes},
            )
        )

    ev_g = _pct_growth(baseline.evidence_dir_bytes, current.evidence_dir_bytes)
    if ev_g >= evidence_warn_pct:
        findings.append(
            DriftFinding(
                "evidence_growth",
                "WARNING",
                f"Evidence directory grew {ev_g}% since baseline",
                {"before": baseline.evidence_dir_bytes, "after": current.evidence_dir_bytes},
            )
        )

    if current.retry_burst_window >= retry_burst_warn:
        findings.append(
            DriftFinding(
                "retry_amplification",
                "WARNING",
                "Retry burst window exceeds threshold",
                {"retry_burst_window": current.retry_burst_window, "threshold": retry_burst_warn},
            )
        )

    for key, after_val in current.counters.items():
        before_val = baseline.counters.get(key, 0)
        if key.endswith("_failures") and after_val - before_val >= 10:
            findings.append(
                DriftFinding(
                    "counter_spike",
                    "WARNING",
                    f"Counter {key} increased by {after_val - before_val}",
                    {"before": before_val, "after": after_val},
                )
            )

    if baseline.rss_bytes and current.rss_bytes:
        rss_g = _pct_growth(int(baseline.rss_bytes), int(current.rss_bytes))
        if rss_g >= 40.0:
            findings.append(
                DriftFinding(
                    "memory_growth",
                    "WARNING",
                    f"RSS grew {rss_g}% since baseline",
                    {"before": baseline.rss_bytes, "after": current.rss_bytes},
                )
            )

    return findings


def build_drift_report(
    findings: list[DriftFinding],
    *,
    baseline: DriftBaseline | None = None,
    current: DriftBaseline | None = None,
) -> dict[str, Any]:
    level: DriftLevel = "OK"
    if any(f.level == "FAIL" for f in findings):
        level = "FAIL"
    elif findings:
        level = "WARNING"

    return {
        "schema_version": DRIFT_REPORT_SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "drift_status": level,
        "finding_count": len(findings),
        "findings": [
            {
                "category": f.category,
                "level": f.level,
                "message": f.message,
                "detail": f.detail,
            }
            for f in findings
        ],
        "baseline_captured_at": baseline.captured_at if baseline else None,
        "current_captured_at": current.captured_at if current else None,
        "anomaly_summary": [f.message for f in findings[:12]],
    }


def write_drift_report(path: Path, report: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_drift_check(
    settings: Any,
    baseline: DriftBaseline,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    current = capture_baseline(settings, output_dir=output_dir)
    findings = compare_baselines(baseline, current)
    return build_drift_report(findings, baseline=baseline, current=current)


def reset_drift_monitor_state_for_tests() -> None:
    """No global state today; hook for future ring buffers."""
    from utils.scheduler_diagnostics import reset_scheduler_diagnostics_for_tests

    reset_scheduler_diagnostics_for_tests()
