#!/usr/bin/env python3
"""Bounded filesystem retention for runtime artifacts, baselines, and reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _path_or_none(p: str | None) -> Path | None:
    if p is None or not str(p).strip():
        return None
    return Path(p)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Runtime retention: prune old zip/json/html outputs under fixed roots (deterministic, no daemon)",
    )
    p.add_argument("--artifacts-dir", type=Path, default=None, help="Directory with bundles + regression/qualification JSON")
    p.add_argument("--baselines-dir", type=Path, default=None, help="Directory with baseline zip bundles")
    p.add_argument("--reports-dir", type=Path, default=None, help="Directory with soak/benchmark/integrity exports")
    p.add_argument("--retain-count", type=int, default=20, help="Per-root: keep newest N matching files after age cut")
    p.add_argument(
        "--max-age-days",
        type=float,
        default=0.0,
        help="Per-root: delete files older than this many days (0 disables age cut)",
    )
    p.add_argument("--dry-run", action="store_true", help="Plan deletions without unlinking files")
    p.add_argument(
        "--include-html",
        action="store_true",
        help="Also consider *.html reports under --reports-dir (basename must contain soak/benchmark/integrity)",
    )
    p.add_argument("--json-output", default="", help="Write retention JSON report to path")
    p.add_argument("--output-report", default="", help="Write human-readable summary")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Non-zero exit if the report contains any warnings",
    )
    args = p.parse_args()

    from utils.runtime_retention import render_retention_summary, run_retention_pass, strict_exit_code

    artifacts = args.artifacts_dir.expanduser().resolve() if args.artifacts_dir else None
    baselines = args.baselines_dir.expanduser().resolve() if args.baselines_dir else None
    reports = args.reports_dir.expanduser().resolve() if args.reports_dir else None

    report = run_retention_pass(
        artifacts_dir=artifacts,
        baselines_dir=baselines,
        reports_dir=reports,
        retain_count=int(args.retain_count),
        max_age_days=float(args.max_age_days),
        include_html=bool(args.include_html),
        dry_run=bool(args.dry_run),
    )
    code = strict_exit_code(report, strict=bool(args.strict))
    print(
        f"scanned={len(report['scanned_files'])} retained={len(report['retained_files'])} "
        f"deleted={len(report['deleted_files'])} reclaimed_bytes={report['reclaimed_bytes']} exit_code={code}",
    )
    if args.json_output.strip():
        outp = Path(args.json_output).expanduser().resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    if args.output_report.strip():
        rep = Path(args.output_report).expanduser().resolve()
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text(render_retention_summary(report), encoding="utf-8")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
