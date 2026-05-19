from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpsPlaybookRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    # --- shift ---
    def get_shift(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_shift_state WHERE id = 1").fetchone()
        return dict(row) if row else None

    def save_shift(
        self,
        *,
        owner_operator_id: str | None,
        handoff: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        started_at: str | None = None,
    ) -> None:
        existing = self.get_shift() or {}
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_shift_state
                (id, owner_operator_id, started_at, handoff_json, unresolved_warnings_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    owner_operator_id,
                    started_at or existing.get("started_at") or _utcnow(),
                    json.dumps(handoff or {}),
                    json.dumps(warnings or []),
                    _utcnow(),
                ),
            )
            conn.commit()

    def record_shift_ack(self, operator_id: str, action: str, detail: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_shift_ack (operator_id, action, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (operator_id, action, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def shift_ack_history(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ops_shift_ack ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- war room ---
    def start_war_room(self, incident_id: str, *, snapshot: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_war_room
                (incident_id, active, started_at, timeline_json, telemetry_json,
                 rollback_recommendation, checklist_json, notes_json)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    _utcnow(),
                    json.dumps([{"t": _utcnow(), "event": "war_room_started"}]),
                    json.dumps(snapshot),
                    "",
                    json.dumps(self._default_checklist()),
                    json.dumps([]),
                ),
            )
            conn.commit()

    @staticmethod
    def _default_checklist() -> dict[str, bool]:
        return {
            "rollout_verified": False,
            "queue_drained": False,
            "telegram_tested": False,
            "openai_budget_checked": False,
            "operator_notified": False,
            "rollback_path_ready": False,
        }

    def get_war_room(self, incident_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_war_room WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        for k in ("timeline_json", "telemetry_json", "checklist_json", "notes_json"):
            if d.get(k):
                d[k.replace("_json", "")] = json.loads(d[k])
        return d

    def active_war_room(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_war_room WHERE active = 1 ORDER BY started_at DESC LIMIT 1",
            ).fetchone()
        return dict(row) if row else None

    def update_war_room(
        self,
        incident_id: str,
        *,
        timeline: list[dict[str, Any]] | None = None,
        notes: list[dict[str, Any]] | None = None,
        checklist: dict[str, bool] | None = None,
        rollback_recommendation: str | None = None,
    ) -> None:
        row = self.get_war_room(incident_id)
        if not row:
            return
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE ops_war_room SET
                timeline_json = ?, notes_json = ?, checklist_json = ?,
                rollback_recommendation = COALESCE(?, rollback_recommendation)
                WHERE incident_id = ?
                """,
                (
                    json.dumps(timeline or row.get("timeline", [])),
                    json.dumps(notes or row.get("notes", [])),
                    json.dumps(checklist or row.get("checklist", {})),
                    rollback_recommendation,
                    incident_id,
                ),
            )
            conn.commit()

    def stop_war_room(self, incident_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE ops_war_room SET active = 0, stopped_at = ? WHERE incident_id = ?",
                (_utcnow(), incident_id),
            )
            conn.commit()

    # --- campaign ---
    def get_campaign(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_campaign_mode WHERE id = 1").fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("config_json"):
            d["config"] = json.loads(d["config_json"])
        return d

    def set_campaign(self, *, active: bool, campaign_type: str | None, config: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_campaign_mode
                (id, active, campaign_type, started_at, config_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    1 if active else 0,
                    campaign_type,
                    _utcnow() if active else None,
                    json.dumps(config),
                    _utcnow(),
                ),
            )
            conn.commit()

    # --- reputation ---
    def save_reputation(
        self,
        *,
        channel_reputation: float,
        trust_volatility: float,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_reputation_snapshots
                (channel_reputation, trust_volatility, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (channel_reputation, trust_volatility, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def latest_reputation(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_reputation_snapshots ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["detail"] = json.loads(d.pop("detail_json", "{}"))
        return d

    # --- audit ---
    def save_audit(self, *, findings: list[dict[str, Any]], compliance_score: float) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO ops_audit_runs (findings_json, compliance_score, created_at)
                VALUES (?, ?, ?)
                """,
                (json.dumps(findings), compliance_score, _utcnow()),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def latest_audit(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_audit_runs ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["findings"] = json.loads(d.pop("findings_json", "[]"))
        return d

    # --- launch period ---
    def get_launch_period(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_launch_period WHERE id = 1").fetchone()
        return dict(row) if row else None

    def init_launch_period(self, *, production_start_at: str, launch_risk: float = 0.5) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO ops_launch_period
                (id, production_start_at, launch_risk_score, protections_active, updated_at)
                VALUES (1, ?, ?, 1, ?)
                """,
                (production_start_at, launch_risk, _utcnow()),
            )
            conn.commit()

    def update_launch_risk(self, score: float, *, protections_active: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE ops_launch_period
                SET launch_risk_score = ?, protections_active = ?, updated_at = ?
                WHERE id = 1
                """,
                (score, 1 if protections_active else 0, _utcnow()),
            )
            conn.commit()

    # --- drills ---
    def save_drill(
        self,
        *,
        scenario: str,
        operator_id: str,
        score: float,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_drill_results
                (scenario, operator_id, score, detail_json, simulated, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (scenario, operator_id, score, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def recent_drills(self, *, limit: int = 5) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ops_drill_results ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- rhythm ---
    def log_rhythm(self, rhythm_type: str, payload: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_rhythm_log (rhythm_type, payload_json, created_at)
                VALUES (?, ?, ?)
                """,
                (rhythm_type, json.dumps(payload), _utcnow()),
            )
            conn.commit()

    def last_rhythm(self, rhythm_type: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM ops_rhythm_log WHERE rhythm_type = ?
                ORDER BY id DESC LIMIT 1
                """,
                (rhythm_type,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["payload"] = json.loads(d.pop("payload_json", "{}"))
        return d
