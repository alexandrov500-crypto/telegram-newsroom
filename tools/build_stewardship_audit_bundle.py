#!/usr/bin/env python3
"""Build offline stewardship audit bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import default_archive_dir, default_reports_dir
from utils.ops_tooling import default_history_dir
from utils.stewardship_audit import build_stewardship_audit_bundle, default_stewardship_audit_root


def main() -> int:
    p = argparse.ArgumentParser(description="Stewardship audit bundle (offline)")
    p.add_argument("--history-dir", default="")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--archive-dir", default="")
    p.add_argument("--audit-root", default="")
    args = p.parse_args()

    try:
        result = build_stewardship_audit_bundle(
            repo_root=REPO,
            history_dir=Path(args.history_dir) if args.history_dir else default_history_dir(REPO),
            reports_dir=Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO),
            archive_dir=Path(args.archive_dir) if args.archive_dir else default_archive_dir(REPO),
            audit_root=Path(args.audit_root) if args.audit_root else default_stewardship_audit_root(REPO),
        )
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    if result.get("freeze_integrity_status") == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
