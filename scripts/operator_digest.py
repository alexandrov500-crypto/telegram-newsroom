#!/usr/bin/env python3
"""Daily operator digest — concise operational overview."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.operator_ux.service import operator_digest_html, save_daily_digest_snapshot
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="Operator operational digest")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    db_path = init_database(args.db or default_db_path())
    snap = save_daily_digest_snapshot(db_path=db_path, base_url=args.base_url)

    if args.json:
        print(json.dumps(snap, indent=2, default=str))
    else:
        print(operator_digest_html(db_path=db_path, base_url=args.base_url))

    try:
        from bot.ops_observation.store import OpsObservationStore

        store = OpsObservationStore()
        out = store.root / "operator_digest.json"
        out.write_text(json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8")
        if not args.json:
            print(f"\nSaved: {out}")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
