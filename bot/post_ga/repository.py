from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostGaRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def save_calibration(
        self,
        *,
        audience: float,
        efficiency: float,
        pacing: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_post_ga_calibration
                (id, audience_responsiveness, publish_efficiency, pacing_json, updated_at)
                VALUES (1, ?, ?, ?, ?)
                """,
                (audience, efficiency, json.dumps(pacing), _utcnow()),
            )
            conn.commit()

    def get_calibration(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_post_ga_calibration WHERE id = 1").fetchone()
        if not row:
            return None
        out = dict(row)
        out["pacing"] = json.loads(out.pop("pacing_json", "{}"))
        return out

    def record_quality_pattern(
        self,
        *,
        source_key: str | None,
        pattern_type: str,
        score: float,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_post_ga_quality_learning
                (source_key, pattern_type, score, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_key, pattern_type, score, json.dumps(detail or {}), _utcnow()),
            )
            conn.commit()

    def source_quality_scores(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT source_key, AVG(score) AS avg_score, COUNT(*) AS n
                FROM ops_post_ga_quality_learning
                WHERE source_key IS NOT NULL
                GROUP BY source_key
                ORDER BY avg_score ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_stability(
        self,
        *,
        autonomy_score: float,
        fatigue_index: float,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_post_ga_stability
                (id, autonomy_score, fatigue_index, detail_json, updated_at)
                VALUES (1, ?, ?, ?, ?)
                """,
                (autonomy_score, fatigue_index, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def get_stability(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_post_ga_stability WHERE id = 1").fetchone()
        if not row:
            return None
        out = dict(row)
        out["detail"] = json.loads(out.pop("detail_json", "{}"))
        return out

    def save_proposal(
        self,
        *,
        proposal_id: str,
        category: str,
        change: dict[str, Any],
        explain: str,
        status: str = "pending",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_post_ga_optimization
                (proposal_id, category, change_json, explain_text, status, operator_id, created_at, applied_at)
                VALUES (?, ?, ?, ?, ?, NULL, ?, NULL)
                """,
                (proposal_id, category, json.dumps(change), explain, status, _utcnow()),
            )
            conn.commit()

    def pending_proposals(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ops_post_ga_optimization WHERE status = 'pending' ORDER BY created_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def apply_proposal(self, proposal_id: str, operator_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE ops_post_ga_optimization
                SET status = 'applied', operator_id = ?, applied_at = ?
                WHERE proposal_id = ?
                """,
                (operator_id, _utcnow(), proposal_id),
            )
            conn.commit()

    def save_risk_forecast(
        self,
        *,
        horizon_hours: float,
        overload_prob: float,
        slo_prob: float,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_post_ga_risk_forecast
                (horizon_hours, overload_prob, slo_violation_prob, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (horizon_hours, overload_prob, slo_prob, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def latest_risk_forecast(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_post_ga_risk_forecast ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["detail"] = json.loads(out.pop("detail_json", "{}"))
        return out

    def save_governance(
        self,
        *,
        trust_trajectory: list[float],
        policy_snapshot: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_post_ga_governance
                (id, trust_trajectory_json, policy_snapshot_json, updated_at)
                VALUES (1, ?, ?, ?)
                """,
                (json.dumps(trust_trajectory[-48:]), json.dumps(policy_snapshot), _utcnow()),
            )
            conn.commit()

    def get_governance(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_post_ga_governance WHERE id = 1").fetchone()
        if not row:
            return None
        out = dict(row)
        out["trust_trajectory"] = json.loads(out.pop("trust_trajectory_json", "[]"))
        out["policy_snapshot"] = json.loads(out.pop("policy_snapshot_json", "{}"))
        return out
