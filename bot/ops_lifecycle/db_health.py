from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


def database_health(db_path: Path) -> dict[str, Any]:
    """SQLite size, table growth, pragma stats. Fail-open."""
    out: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.is_file(),
        "size_bytes": 0,
        "size_mb": 0.0,
        "integrity_ok": False,
        "page_count": 0,
        "freelist_count": 0,
        "tables": {},
        "query_samples_ms": {},
    }
    if not db_path.is_file():
        return out

    out["size_bytes"] = db_path.stat().st_size
    out["size_mb"] = round(out["size_bytes"] / (1024 * 1024), 2)

    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
            out["integrity_ok"] = row is not None and row[0] == "ok"
            out["page_count"] = int(conn.execute("PRAGMA page_count").fetchone()[0])
            out["freelist_count"] = int(conn.execute("PRAGMA freelist_count").fetchone()[0])

            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
                ).fetchall()
            ]
            for table in tables:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    out["tables"][table] = int(count)
                except sqlite3.OperationalError:
                    continue

            probes = [
                ("live_publish_trace", "SELECT COUNT(*) FROM live_publish_trace"),
                ("pending_news", "SELECT COUNT(*) FROM pending_news WHERE status='pending'"),
                ("editorial_storylines", "SELECT COUNT(*) FROM editorial_storylines"),
            ]
            for key, sql in probes:
                try:
                    t0 = time.perf_counter()
                    conn.execute(sql).fetchone()
                    out["query_samples_ms"][key] = round((time.perf_counter() - t0) * 1000, 2)
                except sqlite3.OperationalError:
                    out["query_samples_ms"][key] = None
    except Exception:
        pass
    return out
