#!/usr/bin/env python3
"""Offline publish timeline report from ops metric snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_tooling import (
    build_timeline_report,
    default_history_dir,
    timeline_report_markdown,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Publish timeline report (offline snapshots)")
    p.add_argument("--history-dir", default="")
    p.add_argument("--runtime-dir", default="", help="RUNTIME_STATE_DIR for timeline JSON")
    p.add_argument("--limit", type=int, default=96)
    p.add_argument("--markdown-output", default="")
    p.add_argument("--json-output", default="")
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)
    runtime: Path | None = None
    if args.runtime_dir:
        runtime = Path(args.runtime_dir)
    else:
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO / ".env")
            from app.config import load_settings

            runtime = Path(load_settings().runtime_state_dir)
        except Exception:
            runtime = REPO / "var" / "runtime"

    try:
        report = build_timeline_report(history, runtime_dir=runtime, limit=args.limit)
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1

    md = timeline_report_markdown(report)
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        Path(args.markdown_output).write_text(md, encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(json.dumps(report, indent=2))
        print("\n---\n")
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
