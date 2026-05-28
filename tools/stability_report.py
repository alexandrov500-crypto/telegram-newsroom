#!/usr/bin/env python3
"""Burn-in stability report — variance metrics + PASS/CONDITIONAL/FAIL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.observability.stability_metrics import build_stability_report
from utils.database_url import sqlite_path_from_url


def main() -> int:
    p = argparse.ArgumentParser(description="Stability report for burn-in")
    p.add_argument("--json", action="store_true")
    p.add_argument("--write", type=str, default="", help="Write JSON to path")
    p.add_argument("--log", type=str, default=os.getenv("NEWSROOM_LOG", "logs/local-run.log"))
    p.add_argument("--min-score", type=float, default=60.0)
    args = p.parse_args()

    import sqlite3

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path or not Path(path).is_file():
        out = {"verdict": "FAIL", "reasons": ["database_missing"], "metrics": {}}
        if args.json or args.write:
            text = json.dumps(out, indent=2)
            if args.write:
                Path(args.write).parent.mkdir(parents=True, exist_ok=True)
                Path(args.write).write_text(text, encoding="utf-8")
            print(text)
        else:
            print("FAIL database_missing")
        return 1

    conn = sqlite3.connect(path, timeout=5.0)
    report = build_stability_report(
        conn,
        log_path=args.log,
        runtime_dir=os.getenv("RUNTIME_STATE_DIR", "var/runtime"),
    )
    conn.close()

    score = report.get("metrics", {}).get("system_stability_score", 0)
    verdict = report["verdict"]
    if args.json or args.write:
        text = json.dumps(report, indent=2)
        if args.write:
            wp = Path(args.write)
            wp.parent.mkdir(parents=True, exist_ok=True)
            wp.write_text(text, encoding="utf-8")
        print(text)
    else:
        print(f"{verdict} system_stability_score={score}")
        for r in report.get("reasons") or []:
            print(f"  - {r}")
        m = report.get("metrics") or {}
        print(
            f"  tick_cv={m.get('tick_duration_cv')} "
            f"cadence_cv={m.get('publish_cadence_cv')} "
            f"reject_stability={m.get('reject_reason_stability')} "
            f"running={m.get('running_ticks')}"
        )
        rr = report.get("runtime_resilience") or {}
        print(
            f"  uptime_health_score={rr.get('uptime_health_score')} "
            f"protection={rr.get('current_protection_state')} "
            f"recovery_loops={rr.get('recovery_loops')}"
        )

    return {"PASS": 0, "CONDITIONAL": 2, "FAIL": 1}.get(verdict, 1)


if __name__ == "__main__":
    raise SystemExit(main())
