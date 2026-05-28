#!/usr/bin/env python3
"""Golden tick + publish streak verification (read-only)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.database_url import sqlite_path_from_url  # noqa: E402


def _db() -> sqlite3.Connection:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path:
        raise SystemExit("DATABASE_URL must be local SQLite")
    return sqlite3.connect(path, timeout=5.0)


def main() -> int:
    p = argparse.ArgumentParser(description="Golden tick / publish readiness check")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    conn = _db()
    conn.row_factory = sqlite3.Row
    ticks = conn.execute(
        """
        SELECT id, tick_id, status,
               json_extract(detail_json, '$.terminal_state') AS terminal_state,
               json_extract(detail_json, '$.draft_id') AS draft_id,
               datetime(finished_at) AS finished_at
        FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    running = conn.execute(
        "SELECT COUNT(*) FROM pipeline_ticks WHERE finished_at IS NULL"
    ).fetchone()[0]
    golden = [
        t
        for t in ticks
        if t["status"] == "ok"
        and t["terminal_state"] == "committed_draft"
        and t["draft_id"] is not None
    ]
    pub = conn.execute(
        "SELECT id, draft_id, datetime(published_at) AS published_at FROM published_posts ORDER BY id DESC LIMIT 5"
    ).fetchall()
    drafts_pending = conn.execute(
        "SELECT COUNT(*) FROM drafts WHERE status IN ('pending','approved')"
    ).fetchone()[0]
    conn.close()

    blockers: list[str] = []
    if running:
        blockers.append(f"in_flight_ticks:{running}")
    if not golden:
        blockers.append("no_golden_tick_in_window")
    if not pub:
        blockers.append("no_published_posts_in_db")

    out = {
        "golden_ticks": [dict(g) for g in golden[:3]],
        "recent_ticks": [dict(t) for t in ticks],
        "recent_publishes": [dict(p) for p in pub],
        "pending_drafts": drafts_pending,
        "blockers": blockers,
        "ready": not blockers,
    }

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("=== GOLDEN TICK CHECK ===")
        print(f"Ready: {out['ready']}")
        if blockers:
            print("Blockers:")
            for b in blockers:
                print(f"  - {b}")
        print(f"In-flight ticks: {running}")
        print(f"Pending/approved drafts: {drafts_pending}")
        print("\nLast ticks:")
        for t in ticks:
            mark = " *GOLDEN*" if t in golden else ""
            print(
                f"  id={t['id']} {t['status']} {t['terminal_state']} "
                f"draft_id={t['draft_id']} {t['finished_at']}{mark}"
            )
        print("\nRecent publishes:")
        for p in pub:
            print(f"  draft_id={p['draft_id']} at {p['published_at']}")

    return 0 if out["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
