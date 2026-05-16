"""APScheduler execution diagnostics (opt-in, in-process ring buffer)."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

_lock = threading.RLock()
_runs: deque[dict[str, Any]] = deque(maxlen=128)
_overlap_count = 0


@dataclass(frozen=True)
class SchedulerRunRecord:
    job_id: str
    started_monotonic: float
    finished_monotonic: float
    wall_sec: float
    overlapped: bool
    error: str | None = None


def reset_scheduler_diagnostics_for_tests() -> None:
    global _overlap_count
    with _lock:
        _runs.clear()
        _overlap_count = 0


def record_scheduler_run(
    job_id: str,
    *,
    wall_sec: float,
    error: str | None = None,
    expected_interval_sec: float | None = None,
) -> SchedulerRunRecord:
    global _overlap_count
    now = time.monotonic()
    started = now - wall_sec
    overlapped = False
    with _lock:
        if _runs:
            last = _runs[-1]
            if last.get("job_id") == job_id and last.get("finished_monotonic", 0) > started:
                overlapped = True
                _overlap_count += 1
        rec = {
            "job_id": job_id,
            "started_monotonic": started,
            "finished_monotonic": now,
            "wall_sec": round(wall_sec, 4),
            "overlapped": overlapped,
            "error": error,
            "lag_sec": None,
        }
        if expected_interval_sec and _runs:
            prev = [r for r in _runs if r.get("job_id") == job_id]
            if prev:
                gap = started - float(prev[-1].get("finished_monotonic", started))
                rec["lag_sec"] = round(gap - expected_interval_sec, 4)
        _runs.append(rec)
    return SchedulerRunRecord(
        job_id=job_id,
        started_monotonic=started,
        finished_monotonic=now,
        wall_sec=wall_sec,
        overlapped=overlapped,
        error=error,
    )


def scheduler_diagnostics_snapshot() -> dict[str, Any]:
    with _lock:
        runs = list(_runs)
    if not runs:
        return {"run_count": 0, "overlap_total": _overlap_count, "jobs": {}}
    by_job: dict[str, list[float]] = {}
    for r in runs:
        by_job.setdefault(str(r["job_id"]), []).append(float(r["wall_sec"]))
    return {
        "run_count": len(runs),
        "overlap_total": _overlap_count,
        "jobs": {
            jid: {
                "count": len(walls),
                "wall_sec_max": round(max(walls), 4),
                "wall_sec_avg": round(sum(walls) / len(walls), 4),
            }
            for jid, walls in by_job.items()
        },
        "recent": runs[-8:],
    }


def detect_scheduler_overlap() -> bool:
    with _lock:
        return _overlap_count > 0


def execution_lag_report(*, job_id: str, expected_interval_sec: float) -> dict[str, Any]:
    with _lock:
        job_runs = [r for r in _runs if r.get("job_id") == job_id]
    if len(job_runs) < 2:
        return {"job_id": job_id, "samples": len(job_runs), "lag_status": "insufficient_data"}
    gaps = []
    for i in range(1, len(job_runs)):
        gaps.append(
            float(job_runs[i]["started_monotonic"]) - float(job_runs[i - 1]["finished_monotonic"])
        )
    avg_gap = sum(gaps) / len(gaps)
    lag = avg_gap - expected_interval_sec
    status = "OK" if abs(lag) < expected_interval_sec * 0.25 else "WARNING"
    return {
        "job_id": job_id,
        "samples": len(job_runs),
        "avg_gap_sec": round(avg_gap, 4),
        "expected_interval_sec": expected_interval_sec,
        "lag_sec": round(lag, 4),
        "lag_status": status,
    }
