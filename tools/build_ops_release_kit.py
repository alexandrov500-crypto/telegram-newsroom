#!/usr/bin/env python3
"""Build portable offline operational release kit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import default_archive_dir, default_reports_dir
from utils.ops_release_kit import build_ops_release_kit, default_release_kit_root, verify_release_kit_checksums
from utils.ops_tooling import default_history_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Build offline ops release kit")
    p.add_argument("--history-dir", default="")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--archive-dir", default="")
    p.add_argument("--kit-root", default="")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()

    history = Path(args.history_dir) if args.history_dir else default_history_dir(REPO)
    reports = Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO)
    archive = Path(args.archive_dir) if args.archive_dir else default_archive_dir(REPO)
    kit_root = Path(args.kit_root) if args.kit_root else default_release_kit_root(REPO)

    try:
        result = build_ops_release_kit(
            history_dir=history,
            reports_dir=reports,
            archive_dir=archive,
            kit_root=kit_root,
            limit=args.limit,
        )
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1

    kit_dir = Path(result["kit_dir"])
    ok, errors = verify_release_kit_checksums(kit_dir)
    result["checksum_verify"] = ok
    if not ok:
        result["checksum_errors"] = errors

    print(json.dumps(result, indent=2))
    if result.get("validation_status") == "FAIL":
        return 1
    if not result.get("checksum_verify", True):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
