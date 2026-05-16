#!/usr/bin/env python3
"""Compare two runtime artifact bundles (baseline vs current) for operational regression."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(description="Lightweight runtime baseline regression check (zip bundles)")
    p.add_argument("--current", required=True, type=Path, help="Current runtime_bundle.zip")
    p.add_argument("--baseline", required=True, type=Path, help="Baseline runtime_bundle.zip")
    p.add_argument("--warning-threshold-pct", type=float, default=15.0, help="Pct increase vs baseline → WARNING")
    p.add_argument("--fail-threshold-pct", type=float, default=50.0, help="Pct increase vs baseline → FAIL")
    p.add_argument("--json-output", default="", help="Write full comparison JSON to path")
    p.add_argument("--output-report", default="", help="Write human-readable regression report")
    p.add_argument("--strict", action="store_true", help="Non-zero exit if not fully OK or bundle load warnings")
    p.add_argument("--ignore-missing", action="store_true", help="Treat missing baseline/current metric values as OK")
    args = p.parse_args()

    from utils.runtime_regression import render_regression_report, run_regression_comparison

    payload, code = run_regression_comparison(
        args.baseline.expanduser().resolve(),
        args.current.expanduser().resolve(),
        warn_pct=float(args.warning_threshold_pct),
        fail_pct=float(args.fail_threshold_pct),
        strict=bool(args.strict),
        ignore_missing=bool(args.ignore_missing),
    )
    print(f"overall_status={payload['overall_status']} exit_code={code}")
    nw = len(payload.get("warnings") or [])
    if nw:
        print(f"warnings={nw}")
        for w in (payload.get("warnings") or [])[:12]:
            print(f"  {w}")
    if args.json_output.strip():
        outp = Path(args.json_output).expanduser().resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    if args.output_report.strip():
        rep = Path(args.output_report).expanduser().resolve()
        rep.parent.mkdir(parents=True, exist_ok=True)
        txt = render_regression_report(
            list(payload["metrics"]),
            str(payload["overall_status"]),  # type: ignore[arg-type]
            baseline_label=str(payload["baseline_bundle"]),
            current_label=str(payload["current_bundle"]),
        )
        rep.write_text(txt, encoding="utf-8")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
