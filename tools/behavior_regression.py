#!/usr/bin/env python3
"""Offline behavioral regression testing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    from app.config import load_settings
    from ops.trust.behavior_regression import run_behavior_regression

    parser = argparse.ArgumentParser(description="Behavior regression (deterministic, offline-safe)")
    parser.add_argument("--hours", type=float, default=None, help="Replay window hours")
    parser.add_argument("--save-baseline", action="store_true", help="Update baseline snapshot")
    parser.add_argument("-o", "--output", default="", help="Report path override")
    args = parser.parse_args()
    settings = load_settings()
    report = run_behavior_regression(
        settings.runtime_state_dir,
        window_hours=args.hours,
        save_baseline=args.save_baseline,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report.get("passed"), "diff_count": report.get("diff_count"), "path": str(
        __import__("ops.trust.paths", fromlist=["regression_report_path"]).regression_report_path(settings.runtime_state_dir)
    )}, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
