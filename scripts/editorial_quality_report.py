#!/usr/bin/env python3
"""Daily editorial quality report for operator visibility."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.editorial.quality.fatigue import dominant_topics
from bot.editorial.quality.repository import EditorialQualityRepository
from bot.editorial.quality.service import build_daily_editorial_snapshot, get_editorial_quality_repo
from bot.storage.db import default_db_path, init_database


def _template_ranking(scores: list[dict]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for row in scores:
        counter[str(row.get("template_key") or "unknown")] += 1
    return counter.most_common(8)


def main() -> int:
    bootstrap_env()
    parser = argparse.ArgumentParser(description="Editorial quality operational report")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    db_path = init_database(args.db or default_db_path())
    repo = EditorialQualityRepository(db_path)
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()

    scores = repo.scores_since(hours=args.hours)
    recent = repo.recent_posts(limit=40, hours=args.hours)
    snapshot = build_daily_editorial_snapshot(repo, day=day, hours=args.hours)
    snapshot["dominant_topics"] = dominant_topics(recent)
    snapshot["most_repetitive_templates"] = _template_ranking(scores)
    snapshot["generated_at"] = now.isoformat()
    repo.save_daily_snapshot(day, snapshot)

    # Also mirror into var/ops for observation phase
    try:
        from bot.ops_observation.store import OpsObservationStore

        store = OpsObservationStore()
        editorial_path = store.root / "editorial"
        editorial_path.mkdir(parents=True, exist_ok=True)
        out = editorial_path / f"{day}.json"
        out.write_text(json.dumps(snapshot, indent=2, default=str) + "\n", encoding="utf-8")
        snapshot["artifact_path"] = str(out)
    except Exception:
        pass

    if args.json:
        print(json.dumps(snapshot, indent=2, default=str))
        return 0

    print("=" * 58)
    print(f" EDITORIAL QUALITY REPORT — {day} (last {args.hours}h)")
    print("=" * 58)
    print(f"  posts scored:           {snapshot.get('count', 0)}")
    print(f"  avg quality score:      {snapshot.get('avg_editorial_quality_score')}")
    print(f"  top recurring phrases:  {snapshot.get('top_recurring_phrases', [])[:6]}")
    print(f"  dominant topics:        {snapshot.get('dominant_topics', [])[:6]}")
    print(f"  template breakdown:     {snapshot.get('template_breakdown')}")
    print(f"  source breakdown:       {snapshot.get('source_breakdown')}")
    weakest = snapshot.get("weakest_headlines") or []
    if weakest:
        print("\n  weakest headlines:")
        for row in weakest[:5]:
            print(
                f"    #{row.get('pending_news_id')} "
                f"({row.get('score')}) {row.get('headline', '')[:72]}",
            )
    trend = snapshot.get("quality_score_trend") or []
    if trend:
        print(f"\n  recent score trend:     {', '.join(f'{x:.2f}' for x in trend[:10])}")
    if snapshot.get("artifact_path"):
        print(f"\n  saved: {snapshot['artifact_path']}")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
