#!/usr/bin/env python3
"""Compress and archive aged metrics snapshots (read-only source files)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import archive_snapshots, default_archive_dir, verify_archive_file
from utils.ops_tooling import default_history_dir, list_snapshots, rotate_snapshots


def main() -> int:
    p = argparse.ArgumentParser(description="Archive old ops metrics snapshots")
    p.add_argument("--history-dir", default="")
    p.add_argument("--archive-dir", default="")
    p.add_argument("--older-than-days", type=int, default=14)
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rotate", action="store_true", help="run rotation on active history after archive")
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)
    archive = Path(args.archive_dir) if args.archive_dir else default_archive_dir(REPO)

    if args.verify_only:
        bad = [str(p) for p in archive.rglob("*.json.gz") if not verify_archive_file(p)]
        if bad:
            print(json.dumps({"status": "FAIL", "invalid": bad}, indent=2))
            return 1
        print(json.dumps({"status": "OK", "archives_checked": len(list(archive.rglob("*.json.gz")))}, indent=2))
        return 0

    result = archive_snapshots(history, archive, older_than_days=args.older_than_days)
    rot = {}
    if args.rotate:
        rot = rotate_snapshots(history)
    print(json.dumps({"archive": result, "rotation": rot, "remaining": len(list_snapshots(history))}, indent=2))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
