#!/usr/bin/env python3
"""Operational consolidation report — complexity, contracts, and reduction levers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_consolidation.service import consolidation_html, consolidation_payload
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--contracts-only", action="store_true")
    args = p.parse_args()

    db_path = init_database(args.db or default_db_path())
    if args.contracts_only:
        from bot.ops_consolidation.contracts import subsystem_contracts

        print(json.dumps(subsystem_contracts(), indent=2))
        return 0

    snap = consolidation_payload(db_path=db_path)
    if args.json:
        print(json.dumps(snap, indent=2, default=str))
    else:
        cm = snap.get("complexity_metrics") or {}
        burden = snap.get("maintenance_burden") or {}
        print("=" * 60)
        print(" OPERATIONAL CONSOLIDATION REPORT")
        print("=" * 60)
        print(f"  complexity:    {cm.get('complexity_score')} ({cm.get('complexity_band')})")
        print(f"  loops:         {cm.get('background_loop_count')}")
        print(f"  ops tables:    {cm.get('ops_table_count')}")
        print(f"  commands:      {cm.get('operator_command_count')} ({cm.get('operator_primary_commands')} primary)")
        print(f"  burden:        {burden.get('sustainability')} ({burden.get('overall_burden_score')})")
        print(f"  stability:     {snap.get('stability_phase', {}).get('enabled')}")
        print()
        print(consolidation_html(db_path=db_path))
        print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
