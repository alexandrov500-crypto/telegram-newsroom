#!/usr/bin/env python3
"""CLI: Growth Validation calibration + weekly report preview."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def _run(args: argparse.Namespace) -> int:
    from db.session import init_db, session_scope

    db_url = args.database_url or "sqlite+aiosqlite:///./data/newsroom.db"
    await init_db(db_url)

    from app.growth_layer.validation.service import load_growth_validation_bundle
    from app.growth_layer.validation.weekly_report import build_weekly_growth_report_from_db

    async with session_scope() as session:
        bundle = await load_growth_validation_bundle(session, limit=args.limit)
        if args.weekly:
            text = await build_weekly_growth_report_from_db(session, channel_id=args.channel_id)
            print(text)
        else:
            out = {
                "calibration_30": bundle.calibration_30.to_dict(),
                "calibration_100": bundle.calibration_100.to_dict(),
                "rankings": bundle.rankings.to_dict(),
                "decision": bundle.decision.to_dict(),
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Growth Validation Layer report")
    parser.add_argument("--database-url", default="", help="SQLAlchemy URL (default: local sqlite)")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--weekly", action="store_true", help="Print weekly admin report HTML")
    parser.add_argument("--channel-id", type=int, default=0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
