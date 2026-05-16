#!/usr/bin/env python3
"""CLI entry for controlled soak simulation (operational validation)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    parser = argparse.ArgumentParser(description="Newsroom soak runner (lightweight async simulation)")
    parser.add_argument(
        "--profile",
        choices=("low", "medium", "burst", "noisy_duplicate_storm"),
        default="low",
        help="Synthetic load shape",
    )
    parser.add_argument("--duration-sec", type=float, default=30.0, help="Wall duration (ignored if --max-ticks set)")
    parser.add_argument("--tick-interval-sec", type=float, default=0.1)
    parser.add_argument("--max-ticks", type=int, default=None, help="Hard cap on iterations (preferred for CI-style runs)")
    parser.add_argument("--no-reset-metrics", action="store_true", help="Do not zero in-process metrics before run")
    parser.add_argument("--json-out", type=str, default="", help="Write full JSON report to path")
    parser.add_argument("--html-out", type=str, default="", help="Write HTML summary to path")
    parser.add_argument("--snapshots-max", type=int, default=400, help="Max snapshot rows embedded in reports")
    args = parser.parse_args()

    from app.config import load_settings
    from utils.evidence_reports import build_soak_report
    from utils.soak_simulation import soak_result_to_dict, run_soak_simulation

    settings = load_settings()
    result = asyncio.run(
        run_soak_simulation(
            settings,
            args.profile,
            duration_sec=max(0.05, float(args.duration_sec)),
            tick_interval_sec=max(0.0, float(args.tick_interval_sec)),
            max_ticks=args.max_ticks,
            reset_metrics_at_start=not args.no_reset_metrics,
        )
    )
    full = soak_result_to_dict(result)
    lim = max(1, int(args.snapshots_max))
    if len(full["snapshots"]) > lim:
        full["snapshots"] = full["snapshots"][-lim:]
        full["snapshots_trimmed"] = True
    print(json.dumps({"profile": full["profile"], "ticks": full["ticks"], "warnings": full["warnings"], "bounded": full["bounded_report"]}, indent=2, default=str))
    if args.json_out:
        Path(args.json_out).write_text(build_soak_report(full, format="json"), encoding="utf-8")
    if args.html_out:
        Path(args.html_out).write_text(build_soak_report(full, format="html"), encoding="utf-8")
    return 0 if result.bounded_report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
