#!/usr/bin/env python3
"""Monthly preservation review — evidence-gated, no orchestration."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.editorial.runtime_validation import runtime_validation_snapshot
from bot.editorial.runtime_validation.baseline import load_baseline_history
from bot.editorial.runtime_validation.preservation import (
    build_monthly_stability_review,
    identify_dead_complexity_signals,
)
from bot.operator_ux.collector import collect_operational_context
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser(description="Monthly stability review (preservation mode)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--base-url", default="http://127.0.0.1:8080")
    p.add_argument("--weeks", type=int, default=5, help="Weekly baselines to aggregate")
    p.add_argument("--out-dir", type=Path, default=Path("var/ops/stability"))
    args = p.parse_args()

    history = load_baseline_history(output_dir=args.out_dir, limit=args.weeks)
    db_path = init_database(args.db or default_db_path())
    ctx = collect_operational_context(db_path=db_path, base_url=args.base_url)
    report = runtime_validation_snapshot(ctx=ctx)
    dead = identify_dead_complexity_signals(ctx=ctx)
    review = build_monthly_stability_review(
        weekly_history=history,
        current_report=report,
        dead_complexity=dead,
    )

    if args.json:
        print(json.dumps(review, indent=2, default=str))
        return 0

    print("=" * 60)
    print(f" MONTHLY STABILITY REVIEW — {review.get('month_id')}")
    print("=" * 60)
    print(f"  verdict:        {review.get('monthly_verdict', '?').upper()}")
    print(f"  weeks reviewed: {review.get('weeks_reviewed')}")
    drift = review.get("weekly_baseline_drift") or {}
    print(f"  avg growth:     {drift.get('avg_persistence_growth_rate')}")
    print(f"  avg digest ln:  {drift.get('avg_digest_line_count')}")
    print(f"  validation ok:  {drift.get('validation_stable')}")
    dead_h = (review.get("dead_complexity") or {}).get("dead_complexity_hints") or []
    if dead_h:
        print(f"  dead hints:     {', '.join(dead_h[:4])}")
    print()
    for line in review.get("summary_lines") or []:
        print(f"  • {line}")
    print("=" * 60)
    return 0 if review.get("monthly_verdict") == "stable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
