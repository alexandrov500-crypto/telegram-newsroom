#!/usr/bin/env python3
"""Apply retention policy to forensics tables (dry-run by default)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_forensics.repository import ForensicsRepository


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually delete rows")
    p.add_argument("--timeline-days", type=int, default=30)
    p.add_argument("--snapshot-days", type=int, default=30)
    p.add_argument("--metrics-days", type=int, default=90)
    args = p.parse_args()

    repo = ForensicsRepository()
    plan = [
        ("live_incident_timeline", args.timeline_days),
        ("runtime_state_snapshot", args.snapshot_days),
        ("live_metrics_snapshots", args.metrics_days),
    ]
    for table, days in plan:
        if args.apply:
            n = repo.prune_old_rows(table=table, days=days)
            print(f"pruned {table}: {n} rows older than {days}d")
        else:
            print(f"dry-run would prune {table} > {days}d (use --apply)")
    print("publish traces, audit log, incident bundles: retained (no prune)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
