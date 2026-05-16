#!/usr/bin/env python3
"""Offline analytics aggregation from ops metrics snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import (
    analytics_summary_markdown,
    build_analytics_summary,
    default_reports_dir,
)
from utils.ops_tooling import default_history_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Aggregate ops metrics snapshots (offline)")
    p.add_argument("--history-dir", default="")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--max-age-hours", type=float, default=0.0, help="0 = no filter")
    p.add_argument("--json-output", default="")
    p.add_argument("--md-output", default="")
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)
    reports = Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO)
    reports.mkdir(parents=True, exist_ok=True)

    max_age = args.max_age_hours * 3600.0 if args.max_age_hours > 0 else None
    summary = build_analytics_summary(history, limit=args.limit, max_age_sec=max_age)
    # Drop raw series from JSON export to bound size unless small
    export = {k: v for k, v in summary.items() if k != "series"}
    export["series_count"] = summary.get("snapshot_count")

    json_path = Path(args.json_output) if args.json_output else reports / "analytics_summary.json"
    md_path = Path(args.md_output) if args.md_output else reports / "analytics_summary.md"
    json_path.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(analytics_summary_markdown(summary), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
