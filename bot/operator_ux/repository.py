from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.operator_ux.dedupe import AttentionItem


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttentionMetricsRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def log_attention(
        self,
        item: AttentionItem,
        *,
        delivered: bool,
        suppressed: bool,
    ) -> None:
        now = _utcnow()
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, bundled_count FROM ops_attention_log
                WHERE fingerprint = ? AND last_seen_at >= datetime('now', '-20 minutes')
                ORDER BY last_seen_at DESC LIMIT 1
                """,
                (item.fingerprint,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE ops_attention_log SET
                        bundled_count = bundled_count + 1,
                        suppressed = suppressed + ?,
                        delivered = MAX(delivered, ?),
                        last_seen_at = ?
                    WHERE id = ?
                    """,
                    (1 if suppressed else 0, 1 if delivered else 0, now, row[0]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO ops_attention_log (
                        fingerprint, severity, category, title,
                        bundled_count, delivered, suppressed, created_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.fingerprint,
                        item.severity.value,
                        item.category,
                        item.title[:200],
                        item.count,
                        1 if delivered else 0,
                        1 if suppressed else 0,
                        now,
                        now,
                    ),
                )
            conn.commit()

    def noise_metrics(self, *, hours: int = 24) -> dict[str, int]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(suppressed) AS suppressed,
                    SUM(delivered) AS delivered,
                    SUM(bundled_count) AS bundled,
                    COUNT(*) AS total
                FROM ops_attention_log
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                """,
                (hours,),
            ).fetchone()
        if not row:
            return {"suppressed": 0, "delivered": 0, "bundled": 0, "total": 0}
        return {
            "suppressed": int(row[0] or 0),
            "delivered": int(row[1] or 0),
            "bundled": int(row[2] or 0),
            "total": int(row[3] or 0),
        }

    def save_daily(self, day: str, snapshot: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_attention_daily (date, snapshot_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    created_at = excluded.created_at
                """,
                (day, json.dumps(snapshot), _utcnow()),
            )
            conn.commit()
