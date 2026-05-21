#!/usr/bin/env python3
"""Full runtime snapshot create / restore / list."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def cmd_create(_args: argparse.Namespace) -> int:
    from app.config import load_settings
    from ops.resilience.snapshot import create_snapshot

    settings = load_settings()
    path = create_snapshot(
        runtime_dir=settings.runtime_state_dir,
        database_url=settings.database_url,
        extra_metadata={"deployment_profile": settings.deployment_profile},
    )
    print(path)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    from app.config import load_settings
    from ops.resilience.snapshot import restore_snapshot

    settings = load_settings()
    archive = Path(args.snapshot).expanduser()
    if not archive.is_file():
        cand = Path(settings.runtime_state_dir) / "full_snapshots" / args.snapshot
        if cand.is_file():
            archive = cand
    report = restore_snapshot(
        archive,
        runtime_dir=settings.runtime_state_dir,
        database_url=settings.database_url,
        dry_run=bool(args.dry_run),
    )
    import json

    print(json.dumps(report, indent=2))
    return 0 if not report.get("errors") else 1


def cmd_list(_args: argparse.Namespace) -> int:
    from app.config import load_settings
    from ops.resilience.snapshot import list_snapshots

    settings = load_settings()
    for row in list_snapshots(settings.runtime_state_dir):
        print(f"{row['name']}\t{row['size_bytes']}\t{row['mtime_iso']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime snapshot create/restore")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create", help="Create compressed snapshot with manifest").set_defaults(func=cmd_create)
    p_restore = sub.add_parser("restore", help="Restore from snapshot archive")
    p_restore.add_argument("snapshot", help="Path or snap_*.tar.gz name")
    p_restore.add_argument("--dry-run", action="store_true")
    p_restore.set_defaults(func=cmd_restore)
    sub.add_parser("list", help="List snapshots").set_defaults(func=cmd_list)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
