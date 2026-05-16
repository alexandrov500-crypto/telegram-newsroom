#!/usr/bin/env python3
"""Generate read-only shift handoff markdown from snapshot history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import build_shift_handoff, default_reports_dir
from utils.ops_tooling import default_history_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Shift handoff report (offline)")
    p.add_argument("--history-dir", default="")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--output", default="")
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)
    reports = Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO)
    reports.mkdir(parents=True, exist_ok=True)
    out = Path(args.output) if args.output else reports / "shift_handoff.md"
    md = build_shift_handoff(history, hours=args.hours, reports_dir=reports)
    out.write_text(md, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
