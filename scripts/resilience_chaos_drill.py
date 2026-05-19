#!/usr/bin/env python3
"""Safe resilience validation drills — no production mutation by default."""
from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_resilience.coordinator import evaluate_resilience_tick
from bot.ops_resilience.degradation import build_degradation_matrix
from bot.ops_resilience.dependencies import classify_dependencies
from bot.ops_resilience.failure_budget import compute_failure_budgets
from bot.storage.db import init_database


def drill_telegram_outage_pulse() -> dict:
    return {
        "event_loop_lag_max": 0.1,
        "recovery_attempt_count": 0,
        "stalled_loops": [],
        "anomalies": [{"level": "warning", "kind": "telegram"}],
        "http": {"/channel_health": {"status": "error"}},
        "loop_health": {},
    }


def drill_rss_burst_pulse() -> dict:
    return {
        "event_loop_lag_max": 0.55,
        "recovery_attempt_count": 1,
        "stalled_loops": [],
        "anomalies": [],
        "loop_health": {"rss_loop_duration_avg": 48.0},
        "http": {},
    }


def drill_db_contention(db_path: Path) -> bool:
    """Brief exclusive lock — verifies fail-open evaluation."""
    conn = sqlite3.connect(db_path, timeout=1)
    conn.execute("BEGIN IMMEDIATE")
    try:
        snap = evaluate_resilience_tick(db_path=db_path, pulse=drill_rss_burst_pulse(), persist=False)
        ok = "posture" in snap
    finally:
        conn.rollback()
        conn.close()
    return ok


def drill_delayed_write_simulation() -> float:
    start = time.perf_counter()
    time.sleep(0.05)
    return time.perf_counter() - start


async def drill_maintenance_overlap() -> dict:
    from bot.ops_resilience.context import should_suspend_archival

    return {"archival_would_suspend": should_suspend_archival()}


def run_drill(name: str, db_path: Path) -> dict:
    if name == "telegram_outage":
        pulse = drill_telegram_outage_pulse()
    elif name == "rss_burst":
        pulse = drill_rss_burst_pulse()
    elif name == "recovery_storm":
        pulse = {
            "event_loop_lag_max": 0.6,
            "recovery_attempt_count": 8,
            "stalled_loops": ["ingestion"],
            "anomalies": [{"level": "critical"}],
            "loop_health": {},
            "http": {},
        }
    else:
        pulse = {"event_loop_lag_max": 0.2, "recovery_attempt_count": 0, "http": {}}

    deps = classify_dependencies(pulse=pulse, db_path=db_path)
    budgets = compute_failure_budgets(pulse=pulse, events=[], recovery_log=[])
    matrix = build_degradation_matrix(deps, pulse=pulse, failure_budgets=budgets)
    snap = evaluate_resilience_tick(db_path=db_path, pulse=pulse, persist=False)
    return {
        "drill": name,
        "posture": snap.get("posture"),
        "actions": len(matrix),
        "guidance_count": len(snap.get("guidance") or []),
    }


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser(description="Resilience chaos drills (safe)")
    p.add_argument(
        "--drill",
        choices=("all", "telegram_outage", "rss_burst", "recovery_storm", "db_lock", "filesystem"),
        default="all",
    )
    p.add_argument("--db", type=Path, default=None)
    args = p.parse_args()

    from bot.storage.db import default_db_path

    db_path = init_database(args.db or default_db_path())

    drills = ["telegram_outage", "rss_burst", "recovery_storm"]
    if args.drill != "all":
        drills = [args.drill]

    results: list[dict] = []
    for name in drills:
        if name in ("db_lock",):
            continue
        results.append(run_drill(name, db_path))

    if args.drill in ("all", "db_lock"):
        try:
            tmp_db = init_database(Path(tempfile.mkdtemp()) / "lock_test.db")
            ok = drill_db_contention(tmp_db)
            results.append({"drill": "db_lock", "eval_under_lock": ok})
        except Exception as exc:
            results.append({"drill": "db_lock", "error": str(exc)[:120]})

    if args.drill in ("all", "filesystem"):
        delay = drill_delayed_write_simulation()
        results.append({"drill": "filesystem_delay", "simulated_write_sec": round(delay, 3)})

    overlap = asyncio.run(drill_maintenance_overlap())
    results.append({"drill": "maintenance_overlap", **overlap})

    print("Resilience chaos drill results:")
    for r in results:
        print(f"  {r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
