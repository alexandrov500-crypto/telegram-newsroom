#!/usr/bin/env python3
"""Audit event ledger: counts, duplicate fingerprints, recent events."""

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


def main() -> int:
    p = argparse.ArgumentParser(description="Event ledger audit")
    p.add_argument("--runtime-dir", type=Path, default=None)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    runtime_dir = args.runtime_dir or Path(os.getenv("RUNTIME_STATE_DIR", "/data/runtime"))
    runtime_dir = runtime_dir.expanduser().resolve()
    db = runtime_dir / "event_ledger.db"

    report: dict = {"runtime_dir": str(runtime_dir), "db_exists": db.is_file()}
    if not db.is_file():
        print(json.dumps(report, indent=2) if args.json else "event_ledger.db missing")
        return 1

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    by_type = {
        r["event_type"]: r["c"]
        for r in conn.execute(
            "SELECT event_type, COUNT(*) AS c FROM events GROUP BY event_type"
        )
    }
    dup_fp = conn.execute(
        """
        SELECT fingerprint, COUNT(*) AS c FROM events
        WHERE event_type = 'INGESTED'
        GROUP BY fingerprint HAVING c > 1
        LIMIT 10
        """
    ).fetchall()
    recent = conn.execute(
        """
        SELECT event_id, event_type, channel, message_id, fingerprint, timestamp
        FROM events ORDER BY timestamp_unix DESC LIMIT ?
        """,
        (args.limit,),
    ).fetchall()
    conn.close()

    report.update(
        {
            "total_events": sum(by_type.values()),
            "by_type": by_type,
            "duplicate_ingested_fingerprints": [dict(r) for r in dup_fp],
            "recent": [dict(r) for r in recent],
            "jsonl": str(runtime_dir / "ledger.jsonl"),
            "jsonl_exists": (runtime_dir / "ledger.jsonl").is_file(),
        }
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"=== Event ledger audit ({runtime_dir}) ===")
        print(f"total_events: {report['total_events']}")
        for k, v in sorted(by_type.items()):
            print(f"  {k}: {v}")
        if dup_fp:
            print(f"WARNING: {len(dup_fp)} duplicate INGESTED fingerprints (should be 0)")
        else:
            print("duplicate INGESTED fingerprints: none")
        print(f"recent ({args.limit}):")
        for r in recent:
            print(
                f"  {r['timestamp']} {r['event_type']} {r['channel']}:{r['message_id']} "
                f"fp={str(r['fingerprint'])[:12]}..."
            )
        print(f"jsonl mirror: {report['jsonl']} ({'ok' if report['jsonl_exists'] else 'missing'})")
    return 0 if not dup_fp else 2


if __name__ == "__main__":
    raise SystemExit(main())
