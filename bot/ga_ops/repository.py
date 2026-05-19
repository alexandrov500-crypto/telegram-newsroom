from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GaOpsRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def get_traffic_state(self) -> dict[str, Any]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_ga_traffic_state WHERE id = 1").fetchone()
        if row:
            return dict(row)
        return {
            "pressure_level": "PUBLIC_TRAFFIC_SAFE",
            "publishes_hour": 0,
            "global_freeze": 0,
        }

    def set_traffic_state(
        self,
        *,
        pressure_level: str,
        publishes_hour: int,
        global_freeze: bool,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_ga_traffic_state
                (id, pressure_level, publishes_hour, global_freeze, detail_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    pressure_level,
                    publishes_hour,
                    1 if global_freeze else 0,
                    json.dumps(detail or {}),
                    _utcnow(),
                ),
            )
            conn.commit()

    def record_quality(
        self,
        *,
        story_id: int | None,
        pending_news_id: int | None,
        scores: dict[str, float],
        overall: float,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_ga_quality_scores
                (story_id, pending_news_id, headline_score, consistency_score,
                 contradiction_score, toxicity_score, readability_score, overall_score, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    story_id,
                    pending_news_id,
                    scores.get("headline"),
                    scores.get("consistency"),
                    scores.get("contradiction"),
                    scores.get("toxicity"),
                    scores.get("readability"),
                    overall,
                    json.dumps(scores),
                    _utcnow(),
                ),
            )
            conn.commit()

    def quality_trend(self, *, limit: int = 48) -> list[float]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT overall_score FROM ops_ga_quality_scores
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [float(r[0]) for r in rows]

    def quality_for_story(self, story_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM ops_ga_quality_scores WHERE story_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (story_id,),
            ).fetchone()
        return dict(row) if row else None

    def record_feedback(
        self,
        *,
        source_key: str,
        channel_id: int | None,
        feedback_type: str,
        impact: float,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_ga_feedback
                (source_key, channel_id, feedback_type, impact_score, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source_key, channel_id, feedback_type, impact, json.dumps(detail or {}), _utcnow()),
            )
            conn.commit()

    def source_reputation_adjustment(self, source_key: str) -> float:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT impact_score FROM ops_ga_feedback
                WHERE source_key = ? ORDER BY created_at DESC LIMIT 20
                """,
                (source_key,),
            ).fetchall()
        if not rows:
            return 0.0
        return sum(float(r[0]) for r in rows) / len(rows)

    def get_ga_readiness(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_ga_readiness WHERE id = 1").fetchone()
        if not row:
            return None
        out = dict(row)
        out["blockers"] = json.loads(out.pop("blockers_json", "[]"))
        return out

    def set_ga_readiness(self, *, state: str, score: float, blockers: list[str]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_ga_readiness
                (id, state, score, blockers_json, evaluated_at)
                VALUES (1, ?, ?, ?, ?)
                """,
                (state, score, json.dumps(blockers), _utcnow()),
            )
            conn.commit()

    def save_rollback_snapshot(
        self,
        *,
        snapshot_id: str,
        stage: str,
        integrity_hash: str,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_ga_rollback_snapshots
                (snapshot_id, stage, integrity_hash, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, stage, integrity_hash, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def latest_rollback_snapshot(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_ga_rollback_snapshots ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["detail"] = json.loads(out.pop("detail_json", "{}"))
        return out

    def record_retention_run(self, *, run_id: str, policy: str, rows: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_ga_retention_runs
                (run_id, policy, rows_affected, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, policy, rows, _utcnow()),
            )
            conn.commit()

    def prune_old_slo_snapshots(self, *, keep_days: int = 14) -> int:
        cutoff = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            before = conn.total_changes
            conn.execute(
                """
                DELETE FROM ops_slo_snapshots
                WHERE created_at < datetime(?, '-' || ? || ' days')
                """,
                (cutoff, keep_days),
            )
            conn.commit()
            return conn.total_changes - before
