#!/usr/bin/env python3
"""Weekly operational evidence review — subsystem usefulness and tuning guidance."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_evidence.service import archive_weekly_review, weekly_review_html, weekly_review_payload
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser(description="Weekly operational evidence review")
    p.add_argument("--json", action="store_true", help="Emit JSON snapshot")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--hours", type=int, default=168)
    p.add_argument("--base-url", default="http://127.0.0.1:8080")
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--archive", action="store_true", help="Also write var/ops/weekly/*.json")
    args = p.parse_args()

    db_path = init_database(args.db or default_db_path())
    snap = weekly_review_payload(
        db_path=db_path,
        hours=args.hours,
        base_url=args.base_url,
        persist=not args.no_persist,
    )

    if args.archive:
        archive_weekly_review(db_path=db_path)

    if args.json:
        print(json.dumps(snap, indent=2, default=str))
    else:
        conf = snap.get("operational_confidence") or {}
        print("=" * 60)
        print(f" WEEKLY OPERATIONAL REVIEW — {snap.get('week_id', '?')}")
        print("=" * 60)
        print(f"  confidence:     {conf.get('band')} ({conf.get('score')})")
        print(f"  evolution:      {(snap.get('reliability_timeline') or {}).get('direction')}")
        pub = snap.get("publish_trends") or {}
        print(f"  publishes (7d): {pub.get('published', 0)} · success {pub.get('success_rate')}")
        runtime = snap.get("runtime") or {}
        pulse = runtime.get("pulse") or {}
        print(f"  runtime lag:    {pulse.get('event_loop_lag_max')}")
        print(f"  signals ranked: {len(snap.get('signal_effectiveness') or [])}")
        print(f"  noise candidates:{len(snap.get('retirement_candidates') or [])}")
        print(f"  tuning hints:   {len(snap.get('tuning_suggestions') or [])}")
        print()
        print(weekly_review_html(db_path=db_path, hours=args.hours, base_url=args.base_url))
        print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
