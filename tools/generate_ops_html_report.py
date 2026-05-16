#!/usr/bin/env python3
"""Generate single-file static HTML operations report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import default_reports_dir
from utils.ops_bundle import build_ops_html_report, default_bundle_root


def main() -> int:
    p = argparse.ArgumentParser(description="Static HTML ops report")
    p.add_argument("--bundle-dir", default="", help="latest bundle directory")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--output", default="")
    args = p.parse_args()

    reports = Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO)
    bundle: Path | None = None
    if args.bundle_dir:
        bundle = Path(args.bundle_dir)
    else:
        root = default_bundle_root(REPO)
        if root.is_dir():
            dirs = sorted([d for d in root.iterdir() if d.is_dir()])
            bundle = dirs[-1] if dirs else None

    validation: dict = {}
    val_path = (bundle / "validation_report.json") if bundle else reports / "validation_report.json"
    if val_path.is_file():
        validation = json.loads(val_path.read_text(encoding="utf-8"))

    analytics_path = (bundle / "analytics_summary.json") if bundle else reports / "analytics_summary.json"
    html = build_ops_html_report(
        bundle_dir=bundle,
        validation_report=validation,
        analytics_path=analytics_path if analytics_path.is_file() else None,
    )
    out = Path(args.output) if args.output else reports / "operations_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
