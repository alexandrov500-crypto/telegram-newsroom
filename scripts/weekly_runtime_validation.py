#!/usr/bin/env python3
"""Weekly infrastructure validation — observation only, no orchestration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.editorial.runtime_validation import (
    append_baseline_record,
    capture_operational_baseline,
    load_baseline_history,
    runtime_validation_snapshot,
)
from bot.operator_ux.collector import collect_operational_context
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser(description="Weekly runtime validation (stability discipline)")
    p.add_argument("--json", action="store_true", help="Emit full report JSON")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--base-url", default="http://127.0.0.1:8080")
    p.add_argument("--record", action="store_true", help="Append bounded line to var/ops/stability/")
    p.add_argument("--history", type=int, default=0, metavar="N", help="Print last N weekly records")
    p.add_argument("--out-dir", type=Path, default=Path("var/ops/stability"))
    args = p.parse_args()

    if args.history:
        for row in load_baseline_history(output_dir=args.out_dir, limit=args.history):
            print(json.dumps(row, indent=2, default=str))
            print("-" * 40)
        return 0

    db_path = init_database(args.db or default_db_path())
    ctx = collect_operational_context(db_path=db_path, base_url=args.base_url)
    report = runtime_validation_snapshot(ctx=ctx)
    baseline = capture_operational_baseline(report)

    if args.record:
        path = append_baseline_record(baseline, output_dir=args.out_dir)
        print(f"Recorded → {path}")

    if args.json:
        print(json.dumps({"report": report, "baseline": baseline}, indent=2, default=str))
        return 0

    print("=" * 60)
    print(f" WEEKLY RUNTIME VALIDATION — {baseline.get('week_id', '?')}")
    print("=" * 60)
    ok = report.get("infrastructure_validation_ok")
    print(f"  validation:     {'OK' if ok else 'REVIEW'}")
    print(f"  checks:         {report.get('checks_passed')}/{report.get('checks_total')}")
    run = baseline.get("runtime") or {}
    print(f"  restarts:       {run.get('restart_count')} · recovery_active={run.get('recovery_active')}")
    print(f"  scheduler:      {run.get('scheduler_stability')} · stalled={run.get('stalled_loops')}")
    pers = baseline.get("persistence") or {}
    print(f"  metrics_json:   {pers.get('metrics_json_bytes')} bytes · growth={pers.get('persistence_growth_rate')}")
    dig = baseline.get("digest") or {}
    print(f"  digest lines:   {dig.get('digest_line_count')} · noise_drift={dig.get('digest_noise_drift')}")
    calm = baseline.get("calmness") or {}
    print(f"  long_horizon:   {calm.get('long_horizon_calm')} · hidden_entropy={calm.get('hidden_entropy_observed')}")
    print()
    for line in report.get("summary_lines") or []:
        print(f"  • {line}")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
