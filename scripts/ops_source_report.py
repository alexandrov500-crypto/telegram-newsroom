#!/usr/bin/env python3
"""Source quality calibration report (observation only — no penalties)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_observation.store import OpsObservationStore
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=48)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    db_path = default_db_path()
    init_database(db_path)
    sources: dict[str, dict] = {}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            """
            SELECT t.trace_json, t.created_at, r.rating
            FROM live_publish_trace t
            LEFT JOIN live_channel_post_ratings r ON r.pending_news_id = t.pending_news_id
            WHERE t.created_at >= datetime('now', ?)
            """,
            (f"-{args.hours} hours",),
        ):
            try:
                trace = json.loads(row["trace_json"] or "{}")
            except json.JSONDecodeError:
                continue
            src = str(trace.get("source") or "unknown")
            s = sources.setdefault(
                src,
                {
                    "attempts": 0,
                    "published": 0,
                    "guard_pass": 0,
                    "good": 0,
                    "bad": 0,
                },
            )
            s["attempts"] += 1
            if trace.get("published"):
                s["published"] += 1
            if str(trace.get("guard_result", "")).lower() == "pass":
                s["guard_pass"] += 1
            if row["rating"] == "good":
                s["good"] += 1
            elif row["rating"] == "bad":
                s["bad"] += 1

    for src, s in sources.items():
        n = max(1, s["attempts"])
        s["publish_rate"] = round(s["published"] / n, 3)
        s["notes"] = (
            "observe only — no automated penalties during 48h phase"
        )

    report = {
        "window_hours": args.hours,
        "sources": sources,
    }
    store = OpsObservationStore()
    notes = store.load_source_notes()
    notes["sources"] = sources
    notes["updated_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc,
    ).isoformat()
    store.source_notes_path.write_text(
        json.dumps(notes, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Source calibration ({args.hours}h) — observation only")
        for src, s in sorted(sources.items()):
            print(
                f"  {src}: published={s['published']}/{s['attempts']} "
                f"good={s['good']} bad={s['bad']} rate={s.get('publish_rate')}",
            )
        print(f"Saved: {store.source_notes_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
