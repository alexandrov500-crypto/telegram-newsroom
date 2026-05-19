#!/usr/bin/env python3
"""Run operations lifecycle maintenance (retention, archive, optional VACUUM)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_lifecycle.maintenance import run_maintenance_pass
from bot.ops_lifecycle.storage_report import build_ops_storage_html
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Execute retention (default dry-run)")
    p.add_argument("--vacuum", action="store_true", help="Run VACUUM after retention")
    p.add_argument("--no-backup", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--db", type=Path, default=None)
    args = p.parse_args()

    db_path = init_database(args.db or default_db_path())
    summary = run_maintenance_pass(
        db_path,
        dry_run=not args.apply,
        vacuum=args.vacuum,
        backup=not args.no_backup,
    )

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print("=" * 56)
        print(f" OPS LIFECYCLE MAINTENANCE — {mode}")
        print("=" * 56)
        ent = summary.get("entropy") or {}
        print(f"  rows removed: {ent.get('last_maintenance_rows_removed', 0)}")
        print(f"  vacuum: {summary.get('vacuum')}")
        print(f"  backup: {summary.get('backup_path')}")
        print(f"  pulse: {summary.get('pulse')}")
        print(f"  storyline: {summary.get('storyline')}")
        if summary.get("errors"):
            print(f"  errors: {summary['errors']}")
        print()
        print(build_ops_storage_html(db_path))
        print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
