from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bot.operational_memory.models import IncidentRecord


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationalMemoryRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def ensure_state(self, *, retention_days: int = 90) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO opmem_state (id, retention_days, updated_at)
                VALUES (1, ?, ?)
                """,
                (retention_days, _utcnow()),
            )
            conn.commit()

    def append_incident(self, record: IncidentRecord) -> str:
        iid = record.incident_id or str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO opmem_incidents
                (incident_id, incident_type, severity, started_at, ended_at, duration_sec,
                 affected_subsystems_json, metrics_snapshot_json, survivability_score,
                 confidence_trend, root_cause_candidate, operator_actions_json,
                 recovery_duration_sec, fingerprint_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    iid,
                    record.incident_type,
                    record.severity,
                    record.started_at,
                    record.ended_at,
                    record.duration_sec,
                    json.dumps(record.affected_subsystems),
                    json.dumps(record.metrics_snapshot),
                    record.survivability_score,
                    record.confidence_trend,
                    record.root_cause_candidate,
                    json.dumps(record.operator_actions),
                    record.recovery_duration_sec,
                    record.fingerprint_hash,
                    _utcnow(),
                ),
            )
            conn.commit()
        return iid

    def close_incident(
        self,
        incident_id: str,
        *,
        recovery_duration_sec: float | None,
        operator_actions: list[str] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE opmem_incidents SET
                ended_at = ?, recovery_duration_sec = ?,
                operator_actions_json = COALESCE(?, operator_actions_json)
                WHERE incident_id = ?
                """,
                (
                    _utcnow(),
                    recovery_duration_sec,
                    json.dumps(operator_actions) if operator_actions else None,
                    incident_id,
                ),
            )
            conn.commit()

    def list_incidents(self, *, limit: int = 30, incident_type: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if incident_type:
                rows = conn.execute(
                    """
                    SELECT * FROM opmem_incidents WHERE incident_type = ?
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (incident_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM opmem_incidents ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def upsert_fingerprint(
        self,
        *,
        signature_hash: str,
        pattern_name: str,
        confidence: float,
        avg_impact: float,
        typical_recovery_sec: float | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT recurrence_count FROM opmem_fingerprints WHERE signature_hash = ?",
                (signature_hash,),
            ).fetchone()
            count = (int(row[0]) + 1) if row else 1
            conn.execute(
                """
                INSERT OR REPLACE INTO opmem_fingerprints
                (signature_hash, pattern_name, confidence, recurrence_count, last_seen_at,
                 avg_impact, typical_recovery_sec, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signature_hash,
                    pattern_name,
                    confidence,
                    count,
                    _utcnow(),
                    avg_impact,
                    typical_recovery_sec,
                    json.dumps(detail or {}),
                ),
            )
            conn.commit()

    def list_fingerprints(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM opmem_fingerprints
                ORDER BY recurrence_count DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_fingerprint(self, signature_hash: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM opmem_fingerprints WHERE signature_hash = ?",
                (signature_hash,),
            ).fetchone()
        return dict(row) if row else None

    def save_prediction(
        self,
        *,
        horizon: str,
        degradation: float,
        rollback: float,
        queue_overflow: float,
        alert_storm: float,
        audience_fatigue: float,
        explain: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO opmem_predictions
                (horizon, risk_degradation, risk_rollback, risk_queue_overflow,
                 risk_alert_storm, risk_audience_fatigue, explain_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    horizon,
                    degradation,
                    rollback,
                    queue_overflow,
                    alert_storm,
                    audience_fatigue,
                    json.dumps(explain),
                    _utcnow(),
                ),
            )
            conn.commit()

    def latest_predictions(self) -> dict[str, dict[str, Any]]:
        horizons = ("15m", "1h", "6h", "24h")
        out: dict[str, dict[str, Any]] = {}
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            for h in horizons:
                row = conn.execute(
                    """
                    SELECT * FROM opmem_predictions WHERE horizon = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (h,),
                ).fetchone()
                if row:
                    d = dict(row)
                    d["explain"] = json.loads(d.pop("explain_json", "{}"))
                    out[h] = d
        return out

    def save_drift(
        self,
        *,
        domain: str,
        drift_score: float,
        systemic: bool,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO opmem_drift_snapshots
                (domain, drift_score, systemic, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (domain, drift_score, 1 if systemic else 0, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def latest_drift(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT d.* FROM opmem_drift_snapshots d
                INNER JOIN (
                    SELECT domain, MAX(id) AS mid FROM opmem_drift_snapshots GROUP BY domain
                ) x ON d.id = x.mid
                """,
            ).fetchall()
        cols = [
            "id",
            "domain",
            "drift_score",
            "systemic",
            "detail_json",
            "created_at",
        ]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def upsert_seasonality(self, bucket_key: str, profile: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO opmem_seasonality_profiles
                (bucket_key, profile_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (bucket_key, json.dumps(profile), _utcnow()),
            )
            conn.commit()

    def get_seasonality(self, bucket_key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT profile_json FROM opmem_seasonality_profiles WHERE bucket_key = ?",
                (bucket_key,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_recommendation(
        self,
        *,
        proposal_id: str,
        recommendation: str,
        expected_impact: str,
        blast_radius: str,
        rollback_safe: bool,
        confidence: float,
        similar_incidents: list[str],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO opmem_recommendations
                (proposal_id, recommendation, expected_impact, blast_radius, rollback_safe,
                 confidence, similar_incidents_json, approved, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    proposal_id,
                    recommendation,
                    expected_impact,
                    blast_radius,
                    1 if rollback_safe else 0,
                    confidence,
                    json.dumps(similar_incidents),
                    _utcnow(),
                ),
            )
            conn.commit()

    def pending_recommendations(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM opmem_recommendations WHERE approved = 0 ORDER BY created_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def recurrent_types(self, *, min_count: int = 2) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT incident_type, COUNT(*) AS c, AVG(survivability_score) AS avg_surv
                FROM opmem_incidents
                GROUP BY incident_type HAVING c >= ?
                ORDER BY c DESC
                """,
                (min_count,),
            ).fetchall()
        return [
            {"incident_type": r[0], "count": r[1], "avg_survivability": r[2]}
            for r in rows
        ]

    def prune_retention(self, *, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM opmem_incidents WHERE started_at < ?",
                (cutoff,),
            )
            conn.execute(
                "UPDATE opmem_state SET last_prune_at = ?, updated_at = ? WHERE id = 1",
                (_utcnow(), _utcnow()),
            )
            conn.commit()
            return int(cur.rowcount or 0)
