#!/usr/bin/env python3
"""Backfill post_growth_validation from historical post_performance + growth scores."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _run(args: argparse.Namespace) -> int:
    from app.growth_layer.validation.backfill import backfill_growth_validation
    from db.session import init_db, session_scope

    db_url = args.database_url or "sqlite+aiosqlite:///./data/newsroom.db"
    await init_db(db_url)

    async with session_scope() as session:
        stats = await backfill_growth_validation(
            session,
            dry_run=args.dry_run,
            force=args.force,
            limit=args.limit,
        )
        if not args.skip_segments:
            from app.growth_layer.segments.backfill import backfill_content_segments

            seg_stats = await backfill_content_segments(session, dry_run=args.dry_run, force=args.force)
            summary_seg = seg_stats.to_dict()
            logger.info(
                "segment backfill: scanned=%s updated=%s skipped=%s errors=%s",
                summary_seg["scanned"],
                summary_seg["updated"],
                summary_seg["skipped"],
                summary_seg["errors"],
            )
        if not args.skip_editorial:
            from app.growth_layer.editorial.backfill import backfill_editorial_features

            ed_stats = await backfill_editorial_features(session, dry_run=args.dry_run, force=args.force)
            summary_ed = ed_stats.to_dict()
            logger.info(
                "editorial backfill: scanned=%s updated=%s skipped=%s errors=%s",
                summary_ed["scanned"],
                summary_ed["updated"],
                summary_ed["skipped"],
                summary_ed["errors"],
            )

    summary = stats.to_dict()
    logger.info(
        "backfill complete: scanned=%s created=%s updated=%s skipped=%s errors=%s dry_run=%s",
        summary["scanned"],
        summary["created"],
        summary["updated"],
        summary["skipped"],
        summary["errors"],
        summary["dry_run"],
    )
    if args.verbose and stats.details:
        for line in stats.details[:50]:
            logger.info("  %s", line)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if stats.errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill post_growth_validation from historical data")
    parser.add_argument("--database-url", default="", help="SQLAlchemy URL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--force", action="store_true", help="Overwrite existing FINAL rows")
    parser.add_argument("--limit", type=int, default=None, help="Max published posts to scan")
    parser.add_argument("--skip-segments", action="store_true", help="Skip content_segment backfill")
    parser.add_argument("--skip-editorial", action="store_true", help="Skip editorial features backfill")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
