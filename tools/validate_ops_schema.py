#!/usr/bin/env python3
"""Validate operational schemas (snapshots, analytics, archives)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import default_archive_dir, default_reports_dir
from utils.ops_schema_governance import (
    build_schema_validation_report,
    validation_report_markdown,
    write_json_deterministic,
)
from utils.ops_tooling import default_history_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Validate ops schemas (offline)")
    p.add_argument("--history-dir", default="")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--archive-dir", default="")
    p.add_argument("--json-output", default="")
    p.add_argument("--md-output", default="")
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)
    reports = Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO)
    archive = Path(args.archive_dir) if args.archive_dir else default_archive_dir(REPO)

    report = build_schema_validation_report(history_dir=history, reports_dir=reports, archive_dir=archive)
    json_path = Path(args.json_output) if args.json_output else reports / "validation_report.json"
    md_path = Path(args.md_output) if args.md_output else reports / "validation_report.md"
    reports.mkdir(parents=True, exist_ok=True)
    write_json_deterministic(json_path, report)
    md_path.write_text(validation_report_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report.get("status"), "json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0 if report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
