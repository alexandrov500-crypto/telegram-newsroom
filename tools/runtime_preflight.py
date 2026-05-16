#!/usr/bin/env python3
"""Runtime preflight: bounded startup readiness checks (no daemon, no orchestration)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(description="Runtime preflight — deterministic startup diagnostics")
    p.add_argument("--runtime-dir", type=Path, default=None, help="RUNTIME_STATE_DIR (optional if env loads)")
    p.add_argument("--artifacts-dir", type=Path, default=None, help="Artifacts root (optional)")
    p.add_argument("--reports-dir", type=Path, default=None, help="Reports root (optional)")
    p.add_argument("--check-redis", action="store_true", help="Ping Redis when enabled in settings (bounded timeout)")
    p.add_argument("--check-disk-space", action="store_true", help="Check free disk space at runtime-dir anchor")
    p.add_argument("--min-free-mb", type=float, default=100.0, help="Minimum free disk space (MB) when disk check enabled")
    p.add_argument("--json-output", default="", help="Write JSON report path")
    p.add_argument("--output-report", default="", help="Write human-readable report path")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Non-zero exit unless overall_status is OK (warnings fail the exit)",
    )
    args = p.parse_args()

    from utils.runtime_preflight import evaluate_preflight, render_preflight_report, strict_preflight_exit_code

    settings = None
    err: str | None = None
    try:
        from app.config import load_settings

        settings = load_settings()
    except Exception as exc:
        err = repr(exc)

    report = evaluate_preflight(
        runtime_dir=args.runtime_dir.expanduser().resolve() if args.runtime_dir else None,
        artifacts_dir=args.artifacts_dir.expanduser().resolve() if args.artifacts_dir else None,
        reports_dir=args.reports_dir.expanduser().resolve() if args.reports_dir else None,
        settings=settings,
        settings_load_error=err,
        check_redis=bool(args.check_redis),
        check_disk_space=bool(args.check_disk_space),
        min_free_mb=float(args.min_free_mb),
    )
    code = strict_preflight_exit_code(report, strict=bool(args.strict))
    print(
        f"overall_status={report['overall_status']} preflight_ok={str(report['preflight_ok']).lower()} exit_code={code}",
    )
    if args.json_output.strip():
        outp = Path(args.json_output).expanduser().resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    if args.output_report.strip():
        rep = Path(args.output_report).expanduser().resolve()
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text(render_preflight_report(report), encoding="utf-8")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
