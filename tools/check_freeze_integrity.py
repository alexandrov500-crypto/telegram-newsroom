#!/usr/bin/env python3
"""Check v3.2 freeze integrity (runtime isolation, tooling offline)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.freeze_integrity import (
    build_freeze_integrity_report,
    integrity_report_markdown,
    write_json_deterministic,
)
from utils.ops_analytics import default_reports_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Freeze integrity check (offline)")
    p.add_argument("--json-output", default="")
    p.add_argument("--md-output", default="")
    args = p.parse_args()

    report = build_freeze_integrity_report(REPO)
    reports = default_reports_dir(REPO)
    reports.mkdir(parents=True, exist_ok=True)
    json_path = Path(args.json_output) if args.json_output else reports / "freeze_integrity_report.json"
    md_path = Path(args.md_output) if args.md_output else reports / "freeze_integrity_report.md"
    write_json_deterministic(json_path, report)
    md_path.write_text(integrity_report_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report.get("status"), "json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0 if report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
