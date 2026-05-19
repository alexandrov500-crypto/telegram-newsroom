from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class ReplayMetrics:
    reconstruction_latency_ms: float
    events_scanned: int
    divergence_rate: float
    storage_rows: int


class ReplaySustainability:
    """Replay compaction, snapshots, and acceleration indexes."""

    def __init__(self, db_path: Path, repository: OperationsRepository) -> None:
        self._db_path = db_path
        self._repo = repository

    def create_snapshot(
        self,
        subject_type: str,
        subject_id: str,
        *,
        watermark: int,
        payload: dict,
        tier: str = "hot",
    ) -> str:
        sid = hashlib.sha256(f"{subject_type}:{subject_id}:{watermark}".encode()).hexdigest()[:16]
        self._repo.save_replay_snapshot(
            sid,
            subject_type=subject_type,
            subject_id=subject_id,
            watermark=watermark,
            payload=payload,
            tier=tier,
        )
        return sid

    def ensure_replay_indexes(self) -> list[str]:
        """Idempotent indexes for replay acceleration."""
        statements = [
            "CREATE INDEX IF NOT EXISTS idx_sourced_event_type_time ON sourced_event_log(event_type, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_mesh_events_type ON mesh_cognitive_events(event_type, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_epistemic_scores_updated ON epistemic_scores(updated_at)",
        ]
        applied: list[str] = []
        with sqlite3.connect(self._db_path) as conn:
            for stmt in statements:
                try:
                    conn.execute(stmt)
                    applied.append(stmt.split("idx_")[1].split(" ")[0])
                except sqlite3.OperationalError:
                    pass
            conn.commit()
        return applied

    def measure_replay_health(self) -> ReplayMetrics:
        counts = self._repo.table_row_counts()
        events = counts.get("sourced_event_log", 0) + counts.get("mesh_cognitive_events", 0)
        with sqlite3.connect(self._db_path) as conn:
            try:
                runs = conn.execute("SELECT COUNT(*) FROM epistemic_replay_runs").fetchone()[0]
                failed = conn.execute(
                    "SELECT COUNT(*) FROM epistemic_replay_runs WHERE stability_score < 0.7"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                runs, failed = 0, 0
        divergence = failed / max(runs, 1)
        return ReplayMetrics(
            reconstruction_latency_ms=min(5000.0, events * 0.5),
            events_scanned=events,
            divergence_rate=round(divergence, 4),
            storage_rows=sum(counts.values()),
        )

    def assess_sustainability(self) -> dict:
        health = self.measure_replay_health()
        counts = self._repo.table_row_counts()
        event_rows = counts.get("sourced_event_log", 0) + counts.get("mesh_cognitive_events", 0)
        growth_pressure = min(1.0, event_rows / 500_000)
        score = max(
            0.0,
            min(
                1.0,
                1.0 - health.divergence_rate * 2 - growth_pressure * 0.3,
            ),
        )
        acceleration = growth_pressure > 0.85 or health.divergence_rate > 0.15
        try:
            from bot.observability.metrics import set_replay_sustainability_score

            set_replay_sustainability_score(score)
        except Exception:
            pass
        return {
            "score": round(score, 3),
            "event_rows": event_rows,
            "divergence_rate": health.divergence_rate,
            "storage_acceleration": acceleration,
            "compaction_recommended": event_rows > 250_000,
            "replay_lag_ms": health.reconstruction_latency_ms,
        }

    def summarize_lineage(self, subject_type: str, subject_id: str, max_events: int = 50) -> dict:
        snap = self._repo.get_replay_snapshot(subject_type, subject_id)
        with sqlite3.connect(self._db_path) as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT event_type, created_at FROM sourced_event_log
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (max_events,),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        return {
            "snapshot": snap,
            "recent_events": [{"type": r[0], "at": r[1]} for r in rows],
            "summary": f"{len(rows)} recent sourced events; snapshot={'yes' if snap else 'no'}",
        }
