#!/usr/bin/env python3
"""Persist read-only diagnostics snapshots to var/ops_history."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_tooling import (
    collect_diagnostics_payload,
    default_history_dir,
    persist_snapshot,
    rotate_snapshots,
    summarize_snapshots,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only ops metrics snapshot")
    p.add_argument("--history-dir", default="", help="default: var/ops_history")
    p.add_argument("--rotate", action="store_true", help="apply retention after write")
    p.add_argument("--summary-only", action="store_true", help="print summary, do not write")
    p.add_argument("--max-files", type=int, default=200)
    p.add_argument("--json-output", default="")
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)

    try:
        if args.summary_only:
            out = summarize_snapshots(history)
        else:
            path = persist_snapshot(history, collect_diagnostics_payload())
            rot = {"removed": 0, "kept": 0, "total_bytes": 0}
            if args.rotate:
                rot = rotate_snapshots(history, max_files=args.max_files)
            out = {
                "written": str(path),
                "rotation": rot,
                "summary": summarize_snapshots(history),
            }
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1

    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        Path(args.json_output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
