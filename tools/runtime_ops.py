#!/usr/bin/env python3
"""Unified thin CLI for operational runtime workflows (sequential, same-process, no orchestrator)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--runtime-dir", type=Path, default=None, help="RUNTIME_STATE_DIR root")
    p.add_argument("--artifacts-dir", type=Path, default=None, help="Optional artifacts root for preflight")
    p.add_argument("--reports-dir", type=Path, default=None, help="Optional reports root for preflight / retention")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Writable directory for ops outputs (default: ./runtime_ops_output)",
    )
    p.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline runtime_bundle.zip for regression / qualification steps",
    )
    p.add_argument("--dry-run", action="store_true", help="Skip side-effectful steps where supported")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Non-zero exit on WARNING aggregate or per-step warnings where applicable",
    )
    p.add_argument("--short-soak", action="store_true", help="Use shortened soak profile (nightly / soak)")
    p.add_argument("--skip-retention", action="store_true", help="Skip retention cleanup (nightly-check)")
    p.add_argument(
        "--json-output",
        action="store_true",
        help="Print machine-readable JSON report to stdout instead of human summary",
    )


def main(argv: list[str] | None = None) -> int:
    from utils.runtime_ops import (
        ALL_COMMANDS,
        RuntimeOpsContext,
        ops_exit_code,
        render_runtime_ops_summary,
        run_nightly_check,
        run_single_command,
    )

    parser = argparse.ArgumentParser(
        description="Runtime ops — deterministic sequential wrapper around existing operational tooling",
    )
    parser.add_argument(
        "command",
        choices=list(ALL_COMMANDS),
        help="Operational step or nightly-check (fixed step order)",
    )
    _add_common(parser)
    args = parser.parse_args(argv)

    out = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else (Path.cwd() / "runtime_ops_output").resolve()
    )
    ctx = RuntimeOpsContext(
        output_dir=out,
        runtime_dir=args.runtime_dir.expanduser().resolve() if args.runtime_dir else None,
        artifacts_dir=args.artifacts_dir.expanduser().resolve() if args.artifacts_dir else None,
        reports_dir=args.reports_dir.expanduser().resolve() if args.reports_dir else None,
        baseline=args.baseline.expanduser().resolve() if args.baseline else None,
        dry_run=bool(args.dry_run),
        strict=bool(args.strict),
        short_soak=bool(args.short_soak),
        skip_retention=bool(args.skip_retention),
    )

    if args.command == "nightly-check":
        report = run_nightly_check(ctx)
    else:
        report = run_single_command(args.command, ctx)

    if args.json_output:
        sys.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    else:
        sys.stdout.write(render_runtime_ops_summary(report))

    return ops_exit_code(report, strict=bool(args.strict))


if __name__ == "__main__":
    raise SystemExit(main())
