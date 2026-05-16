#!/usr/bin/env python3
"""Export reproducible offline ops bundle with manifest and checksums."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import default_archive_dir, default_reports_dir
from utils.ops_bundle import default_bundle_root, export_ops_bundle
from utils.ops_tooling import default_history_dir


def main() -> int:
    p = argparse.ArgumentParser(description="Export ops bundle (offline)")
    p.add_argument("--history-dir", default="")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--archive-dir", default="")
    p.add_argument("--bundle-root", default="")
    p.add_argument("--limit", type=int, default=200)
    args = p.parse_args()

    try:
        result = export_ops_bundle(
            history_dir=Path(args.history_dir) if args.history_dir else default_history_dir(REPO),
            reports_dir=Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO),
            archive_dir=Path(args.archive_dir) if args.archive_dir else default_archive_dir(REPO),
            bundle_root=Path(args.bundle_root) if args.bundle_root else default_bundle_root(REPO),
            limit=args.limit,
        )
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("validation_status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
