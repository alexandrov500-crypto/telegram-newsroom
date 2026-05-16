#!/usr/bin/env python3
"""Lightweight operational release decision from runtime artifact bundles (read-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(
        description="Release qualification: derive RELEASE_READY from runtime bundle + baseline (deterministic)",
    )
    p.add_argument("--runtime-bundle", required=True, type=Path, help="Current runtime_bundle.zip")
    p.add_argument("--baseline", required=True, type=Path, help="Baseline runtime_bundle.zip")
    p.add_argument(
        "--warning-threshold-pct",
        type=float,
        default=15.0,
        help="Pct increase vs baseline for WARNING (regression + bounded state sizes)",
    )
    p.add_argument(
        "--fail-threshold-pct",
        type=float,
        default=50.0,
        help="Pct increase vs baseline for FAIL",
    )
    p.add_argument(
        "--allow-warning",
        action="store_true",
        help="Allow qualification WARNING checks and still set release_ready true",
    )
    p.add_argument("--json-output", default="", help="Write qualification JSON to path")
    p.add_argument("--output-report", default="", help="Write human-readable qualification report")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Non-zero exit unless qualification_status is OK and regression has no bundle warnings",
    )
    p.add_argument(
        "--require-soak",
        action="store_true",
        help="Fail if soak_report.json is absent or unhealthy",
    )
    p.add_argument(
        "--require-integrity-clean",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When true (default), missing integrity.json or integrity issues fail qualification",
    )
    p.add_argument(
        "--require-regression-ok",
        action="store_true",
        help="Regression overall must be OK (WARNING fails even with --allow-warning)",
    )
    args = p.parse_args()

    from utils.release_qualification import evaluate_release_qualification, render_release_report

    current = args.runtime_bundle.expanduser().resolve()
    baseline = args.baseline.expanduser().resolve()

    result, code = evaluate_release_qualification(
        current,
        baseline,
        warn_pct=float(args.warning_threshold_pct),
        fail_pct=float(args.fail_threshold_pct),
        allow_warning=bool(args.allow_warning),
        strict=bool(args.strict),
        require_soak=bool(args.require_soak),
        require_integrity_clean=bool(args.require_integrity_clean),
        require_regression_ok=bool(args.require_regression_ok),
    )

    print(f"qualification_status={result['qualification_status']} release_ready={str(result['release_ready']).lower()} exit_code={code}")
    nw = len(result.get("warnings") or [])
    nf = len(result.get("failures") or [])
    if nw:
        print(f"warnings={nw}")
        for w in (result.get("warnings") or [])[:12]:
            print(f"  {w}")
    if nf:
        print(f"failures={nf}")
        for f in (result.get("failures") or [])[:12]:
            print(f"  {f}")

    if args.json_output.strip():
        outp = Path(args.json_output).expanduser().resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    if args.output_report.strip():
        rep = Path(args.output_report).expanduser().resolve()
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text(render_release_report(result), encoding="utf-8")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
