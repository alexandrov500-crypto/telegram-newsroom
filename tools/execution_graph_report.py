#!/usr/bin/env python3
"""Write var/runtime/execution_graph_report.json from DB + trace JSONL + logs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.observability.execution_graph_report import build_execution_graph_report, write_execution_graph_report
from utils.database_url import sqlite_path_from_url


def main() -> int:
    p = argparse.ArgumentParser(description="Execution graph consistency report")
    p.add_argument("--json", action="store_true", help="Print report JSON to stdout")
    p.add_argument("--window", type=int, default=100)
    p.add_argument(
        "--write",
        type=str,
        default="",
        help="Output path (default: RUNTIME_STATE_DIR/execution_graph_report.json)",
    )
    args = p.parse_args()

    runtime_dir = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    db_path = sqlite_path_from_url(raw)
    log_path = Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log"))
    out = Path(args.write) if args.write else runtime_dir / "execution_graph_report.json"

    report = build_execution_graph_report(
        db_path=Path(db_path) if db_path else None,
        runtime_dir=runtime_dir,
        log_path=log_path,
        window_ticks=args.window,
    )
    write_execution_graph_report(
        runtime_dir=runtime_dir,
        db_path=Path(db_path) if db_path else None,
        log_path=log_path,
        out_path=out,
        window_ticks=args.window,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Execution graph: {report['verdict']}")
        print(f"  consistency_rate={report.get('consistency_rate')}")
        print(f"  anomalies_per_100={report.get('anomalies_per_100_ticks')}")
        print(f"  publish_correctness={report.get('publish_correctness_rate')}")
        print(f"  log_anomalies={report.get('log_signals', {}).get('execution_graph_anomaly')}")
        print(f"  written: {out}")

    return 0 if report.get("execution_graph_ready") else (2 if report.get("verdict") == "CONDITIONAL" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
