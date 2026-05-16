#!/usr/bin/env python3
"""Evidence directory retention and archive verification (opt-in operator tool)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _dir_summary(path: Path) -> dict[str, object]:
    if not path.is_dir():
        return {"exists": False, "bytes": 0, "files": 0}
    files = 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            files += 1
            try:
                total += p.stat().st_size
            except OSError:
                continue
    return {"exists": True, "bytes": total, "files": files}


def cmd_report(args: argparse.Namespace) -> int:
    od = Path(args.output_dir).expanduser().resolve()
    rt = od / "runtime"
    report = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "output_dir": str(od),
        "runtime": _dir_summary(rt),
        "sidecars": {
            name: (od / name).is_file()
            for name in (
                "runtime_bundle.zip",
                "qualification.json",
                "ops_benchmark.json",
            )
        },
    }
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    from utils.runtime_retention import run_retention_pass

    artifacts = Path(args.artifacts_dir).expanduser().resolve() if args.artifacts_dir else None
    baselines = Path(args.baselines_dir).expanduser().resolve() if args.baselines_dir else None
    reports = Path(args.reports_dir).expanduser().resolve() if args.reports_dir else None
    rep = run_retention_pass(
        artifacts_dir=artifacts,
        baselines_dir=baselines,
        reports_dir=reports,
        retain_count=int(args.max_count),
        max_age_days=float(args.max_age_hours) / 24.0,
        dry_run=bool(args.dry_run),
        include_html=bool(args.include_html),
    )
    if args.json_output:
        from utils.runtime_retention import render_retention_summary

        Path(args.json_output).write_text(render_retention_summary(rep), encoding="utf-8")
    else:
        print(json.dumps(rep, indent=2, default=str))
    return 0


def cmd_verify_manifest(args: argparse.Namespace) -> int:
    od = Path(args.output_dir).expanduser().resolve()
    manifest_path = od / "runtime" / "runtime_manifest.json"
    if not manifest_path.is_file():
        print("missing runtime_manifest.json", file=sys.stderr)
        return 2
    proc = __import__("subprocess").run(
        [sys.executable, "-m", "newsroom.cli", "verify-runtime", "--path", str(od)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    return proc.returncode


def main() -> int:
    p = argparse.ArgumentParser(description="Evidence retention and verification")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("report", help="Evidence directory sizing report")
    r.add_argument("--output-dir", default="runtime_ops_output")
    r.add_argument("--json-output", default="")
    r.set_defaults(func=cmd_report)

    pr = sub.add_parser("prune", help="Prune CI artifact roots via runtime_retention")
    pr.add_argument("--artifacts-dir", default="")
    pr.add_argument("--baselines-dir", default="")
    pr.add_argument("--reports-dir", default="")
    pr.add_argument("--max-count", type=int, default=32)
    pr.add_argument("--max-age-hours", type=float, default=168)
    pr.add_argument("--max-bytes", type=int, default=500_000_000)
    pr.add_argument("--dry-run", action="store_true")
    pr.add_argument("--include-html", action="store_true")
    pr.add_argument("--json-output", default="")
    pr.set_defaults(func=cmd_prune)

    v = sub.add_parser("verify-manifest", help="Run verify-runtime on OUTPUT_DIR")
    v.add_argument("--output-dir", default="runtime_ops_output")
    v.set_defaults(func=cmd_verify_manifest)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
