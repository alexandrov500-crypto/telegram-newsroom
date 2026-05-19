from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Week1Repository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def init_state(self, *, week_start_at: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO week1_state
                (id, week_start_at, baseline_captured, updated_at)
                VALUES (1, ?, 0, ?)
                """,
                (week_start_at, _utcnow()),
            )
            conn.commit()

    def get_state(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM week1_state WHERE id = 1").fetchone()
        return dict(row) if row else None

    def mark_baseline_captured(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE week1_state SET baseline_captured = 1, updated_at = ? WHERE id = 1",
                (_utcnow(),),
            )
            conn.commit()

    def save_baseline(self, domain: str, snapshot: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO week1_baselines (domain, snapshot_json, captured_at)
                VALUES (?, ?, ?)
                """,
                (domain, json.dumps(snapshot), _utcnow()),
            )
            conn.commit()

    def get_baseline(self, domain: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT snapshot_json FROM week1_baselines WHERE domain = ?",
                (domain,),
            ).fetchone()
        return json.loads(row["snapshot_json"]) if row else None

    def all_baselines(self) -> dict[str, dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT domain, snapshot_json FROM week1_baselines").fetchall()
        return {r["domain"]: json.loads(r["snapshot_json"]) for r in rows}

    def log_alert(
        self,
        *,
        alert_key: str,
        severity: str,
        root_cause: str,
        confidence: float,
        suppressed: bool,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO week1_alert_log
                (alert_key, severity, root_cause, confidence, suppressed, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_key,
                    severity,
                    root_cause,
                    confidence,
                    1 if suppressed else 0,
                    json.dumps(detail),
                    _utcnow(),
                ),
            )
            conn.commit()

    def recent_alerts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM week1_alert_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_quality(self, *, quality: float, fatigue: float, detail: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO week1_quality_snapshots
                (quality_score, fatigue_score, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (quality, fatigue, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def quality_history(self, *, limit: int = 48) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM week1_quality_snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_proposal(
        self,
        *,
        proposal_id: str,
        category: str,
        recommendation: str,
        safety_score: float,
        blast_radius: str,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO week1_optimization_proposals
                (proposal_id, category, recommendation, safety_score, blast_radius,
                 approved, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    proposal_id,
                    category,
                    recommendation,
                    safety_score,
                    blast_radius,
                    json.dumps(detail),
                    _utcnow(),
                ),
            )
            conn.commit()

    def pending_proposals(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM week1_optimization_proposals WHERE approved = 0 ORDER BY created_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def save_survivability(
        self,
        *,
        score: float,
        confidence_trend: float,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO week1_survivability
                (survivability_score, confidence_trend, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (score, confidence_trend, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def survivability_history(self, *, limit: int = 24) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM week1_survivability ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
