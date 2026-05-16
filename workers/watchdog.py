"""Lightweight runtime watchdogs: diagnostics and warnings only (no process control)."""

from __future__ import annotations

from typing import Any


def evaluate_runtime_watchdogs(
    settings: Any,
    *,
    worker_role: str,
    job_kind: str,
    counters: dict[str, Any],
    queue_pressure: dict[str, Any],
) -> list[dict[str, Any]]:
    warns: list[dict[str, Any]] = []
    base = {"worker_role": worker_role, "job_kind": job_kind}

    active = int(counters.get("active_jobs") or 0)
    if active > 0:
        oldest = counters.get("oldest_active_job_age_sec")
        lim = float(getattr(settings, "runtime_active_job_warn_sec", 120))
        if oldest is not None and float(oldest) >= lim:
            warns.append(
                {
                    **base,
                    "code": "long_running_job",
                    "active_jobs": active,
                    "oldest_active_job_age_sec": float(oldest),
                    "threshold_sec": lim,
                }
            )

    last_ok = counters.get("last_success_age_sec")
    stale_lim = float(getattr(settings, "runtime_success_stale_warn_sec", 300))
    if last_ok is not None and float(last_ok) >= stale_lim and active > 0:
        warns.append(
            {
                **base,
                "code": "success_stale_under_load",
                "last_success_age_sec": float(last_ok),
                "threshold_sec": stale_lim,
                "active_jobs": active,
            }
        )

    burst = int(counters.get("retry_burst_window", 0))
    burst_n = int(getattr(settings, "runtime_retry_storm_count", 40))
    if burst >= burst_n:
        warns.append(
            {
                **base,
                "code": "retry_storm",
                "retry_burst_window": burst,
                "threshold": burst_n,
                "window_sec": float(getattr(settings, "runtime_retry_storm_window_sec", 60)),
            }
        )

    pend = int(queue_pressure.get("pending_depth") or 0)
    proc = int(queue_pressure.get("processing_depth") or 0)
    active_jobs = int(counters.get("active_jobs") or 0)
    if pend > 0 and proc == 0 and active_jobs == 0:
        warns.append(
            {
                **base,
                "code": "possible_queue_starvation",
                "pending_depth": pend,
                "processing_depth": proc,
            }
        )

    return warns
