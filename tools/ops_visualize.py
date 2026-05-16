#!/usr/bin/env python3
"""Generate static SVG charts from snapshot history (offline)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import (
    build_analytics_summary,
    build_visualization_bundle,
    default_reports_dir,
)
from utils.ops_tooling import default_history_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Static SVG visualization from snapshots")
    p.add_argument("--history-dir", default="")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--limit", type=int, default=200)
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)
    reports = Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO)
    reports.mkdir(parents=True, exist_ok=True)

    summary = build_analytics_summary(history, limit=args.limit)
    charts = build_visualization_bundle(summary)
    index_lines = ["# Ops visualization index", "", f"Charts: {len(charts)}", ""]
    for name, svg in sorted(charts.items()):
        out = reports / name
        out.write_text(svg, encoding="utf-8")
        index_lines.append(f"- [{name}]({name})")
    (reports / "visualizations.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"wrote {len(charts)} svg under {reports}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
