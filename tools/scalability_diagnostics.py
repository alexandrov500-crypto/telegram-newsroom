#!/usr/bin/env python3
"""Read-only scalability / growth pressure diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _dir_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return total


def _finding(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def run_diagnostics(
    *,
    output_dir: Path | None,
    runtime_state_dir: Path | None,
    database_url_hint: str = "",
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    metrics: dict[str, Any] = {}

    # Topology hint
    if _env_truthy("REDIS_ENABLED"):
        topo = "T2" if _env_truthy("PUBLISH_LOCK_STRICT") and _env_truthy("WORKER_RETRY_SAFE") else "T2-risky"
    else:
        topo = "T1"
    metrics["topology_hint"] = topo

    storm_n = int(os.environ.get("RUNTIME_RETRY_STORM_COUNT", "40"))
    storm_w = float(os.environ.get("RUNTIME_RETRY_STORM_WINDOW_SEC", "60"))
    metrics["retry_storm_threshold"] = {"count": storm_n, "window_sec": storm_w}

    try:
        import asyncio
        from workers import state as worker_state

        async def _burst() -> int:
            return int((await worker_state.collect_runtime_diag(type("S", (), {})())).get("retry_burst_window", 0))

        try:
            asyncio.get_running_loop()
            burst = 0
        except RuntimeError:
            burst = asyncio.run(_burst())
        metrics["retry_burst_window"] = burst
        if burst >= storm_n:
            findings.append(
                _finding(
                    "HIGH",
                    "retry_saturation",
                    f"retry_burst_window={burst} >= threshold {storm_n}",
                    "See runbooks/scaling/RETRY_SATURATION.md; fix upstream failures",
                )
            )
    except Exception:
        pass

    if output_dir and output_dir.is_dir():
        od = output_dir.expanduser().resolve()
        rt_bytes = _dir_bytes(od / "runtime")
        od_bytes = _dir_bytes(od)
        metrics["output_dir_bytes"] = od_bytes
        metrics["runtime_subtree_bytes"] = rt_bytes
        if od_bytes > 500_000_000:
            findings.append(
                _finding(
                    "MEDIUM",
                    "evidence_growth",
                    f"OUTPUT_DIR size {od_bytes} bytes exceeds 500MB heuristic",
                    "Run evidence_retention prune; archive old nightly outputs",
                )
            )
        if rt_bytes > 100_000_000:
            findings.append(
                _finding(
                    "LOW",
                    "snapshot_size_warning",
                    f"runtime/ subtree {rt_bytes} bytes — snapshot/restore will be slower",
                    "See SNAPSHOT_SIZE_GROWTH runbook",
                )
            )

    if database_url_hint or "sqlite" in database_url_hint.lower():
        from utils.runtime_drift_monitor import _sqlite_wal_bytes

        wal = _sqlite_wal_bytes(database_url_hint or os.environ.get("DATABASE_URL", ""))
        metrics["wal_bytes"] = wal
        if wal > 268_435_456:
            findings.append(
                _finding(
                    "HIGH",
                    "wal_pressure",
                    f"SQLite WAL {wal} bytes > 256MB",
                    "Quiesce and PRAGMA wal_checkpoint; see WAL_PRESSURE runbook",
                )
            )

    try:
        from utils.scheduler_diagnostics import detect_scheduler_overlap, scheduler_diagnostics_snapshot

        snap = scheduler_diagnostics_snapshot()
        metrics["scheduler"] = snap
        if detect_scheduler_overlap():
            findings.append(
                _finding(
                    "MEDIUM",
                    "scheduler_saturation",
                    "Scheduler job overlap detected",
                    "See SCHEDULER_SATURATION runbook; reduce pipeline interval or job duration",
                )
            )
    except Exception:
        pass

    if _env_truthy("REDIS_ENABLED") and not _env_truthy("PUBLISH_LOCK_STRICT"):
        findings.append(
            _finding(
                "HIGH",
                "multi_worker_contention_risk",
                "Redis queue without PUBLISH_LOCK_STRICT",
                "Enable PUBLISH_LOCK_STRICT=1 for multi-worker publish safety",
            )
        )

    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    worst = max((order.get(f["severity"], 0) for f in findings), default=0)
    status = "FAIL" if worst >= 3 else ("WARNING" if findings else "OK")
    return {
        "schema_version": 1,
        "read_only": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "topology_hint": topo,
        "metrics": metrics,
        "findings": findings,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="")
    p.add_argument("--runtime-state-dir", default="")
    p.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    p.add_argument("--json-output", default="")
    p.add_argument("--fail-on", default="HIGH")
    args = p.parse_args()

    od = Path(args.output_dir) if args.output_dir else None
    rsd = Path(args.runtime_state_dir) if args.runtime_state_dir else None
    report = run_diagnostics(
        output_dir=od,
        runtime_state_dir=rsd,
        database_url_hint=args.database_url,
    )

    fail_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    threshold = fail_order.get(args.fail_on.upper(), 3)
    worst = 0
    for f in report.get("findings") or []:
        worst = max(worst, fail_order.get(str(f.get("severity")), 0))
    if worst >= threshold and report.get("findings"):
        report["status"] = "FAIL"

    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0 if report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
