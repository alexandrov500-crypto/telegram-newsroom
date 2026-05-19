from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.operations.repository import OperationsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompactionResult:
    table: str
    rows_before: int
    rows_after: int
    policy: str


class StorageSustainability:
    """Bounded storage growth with replay-safe retention."""

    RETENTION_DAYS = {
        "mesh_cognitive_events": 30,
        "evaluation_traces": 60,
        "epistemic_confidence_log": 90,
        "ops_burnin_samples": 45,
        "topology_snapshots": 30,
    }

    def __init__(self, db_path: Path, repository: OperationsRepository) -> None:
        self._db_path = db_path
        self._repo = repository

    def snapshot_tables(self) -> dict[str, int]:
        counts = self._repo.table_row_counts()
        for table, count in counts.items():
            self._repo.record_storage_snapshot(table, count, estimated_bytes=count * 512)
        return counts

    def compact_table(self, table: str, *, retention_days: int | None = None) -> CompactionResult | None:
        days = retention_days or self.RETENTION_DAYS.get(table, 30)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        time_col = "created_at"
        if table == "mesh_cognitive_events":
            time_col = "created_at"

        with sqlite3.connect(self._db_path) as conn:
            try:
                before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                return None
            try:
                conn.execute(
                    f"DELETE FROM {table} WHERE {time_col} < ?",
                    (cutoff,),
                )
                after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.commit()
            except sqlite3.OperationalError as exc:
                logger.warning("event=compaction_skipped table=%s error=%s", table, exc)
                return None

        policy = f"retain_{days}d"
        self._repo.log_compaction(table, before, after, policy)
        return CompactionResult(table, before, after, policy)

    def run_maintenance(self) -> list[CompactionResult]:
        results: list[CompactionResult] = []
        for table in self.RETENTION_DAYS:
            r = self.compact_table(table)
            if r:
                results.append(r)
        self.snapshot_tables()
        return results

    def estimate_growth_mb_per_day(self) -> float:
        with sqlite3.connect(self._db_path) as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT estimated_bytes, created_at FROM ops_storage_snapshots
                    ORDER BY created_at DESC LIMIT 200
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                return 0.0
        if len(rows) < 2:
            return 0.0
        newest = rows[0][0]
        oldest = rows[-1][0]
        return max(0.0, (newest - oldest) / (1024 * 1024) / max(len(rows), 1))
