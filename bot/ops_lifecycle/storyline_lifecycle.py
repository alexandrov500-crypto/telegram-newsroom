from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def archive_idle_storylines(
    db_path: Path,
    *,
    idle_days: int = 60,
    dry_run: bool = False,
    keep_events_per_storyline: int = 5,
) -> dict[str, int]:
    """
    Compact long-idle storylines: keep latest N events, archive summary, reduce row count.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=idle_days)).isoformat()
    stats = {"storylines_touched": 0, "events_removed": 0}
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT storyline_id, title, publish_count, last_updated_at
                FROM editorial_storylines
                WHERE last_updated_at < ?
                """,
                (cutoff,),
            ).fetchall()
        except sqlite3.OperationalError:
            return stats

        for row in rows:
            sid = row["storyline_id"]
            stats["storylines_touched"] += 1
            events = conn.execute(
                """
                SELECT id, headline, created_at FROM editorial_story_events
                WHERE storyline_id = ?
                ORDER BY created_at DESC
                """,
                (sid,),
            ).fetchall()
            if len(events) <= keep_events_per_storyline:
                continue
            to_remove = events[keep_events_per_storyline:]
            if dry_run:
                stats["events_removed"] += len(to_remove)
                continue
            summary = {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "title": row["title"],
                "events_archived": len(to_remove),
                "publish_count": row["publish_count"],
            }
            from bot.ops_lifecycle.repository import LifecycleRepository

            LifecycleRepository(db_path).save_daily_summary(
                datetime.now(timezone.utc).date().isoformat(),
                f"storyline:{sid}",
                summary,
            )
            ids = [int(e["id"]) for e in to_remove]
            conn.execute(
                f"DELETE FROM editorial_story_events WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
            stats["events_removed"] += len(ids)

        if not dry_run:
            conn.commit()
    return stats
