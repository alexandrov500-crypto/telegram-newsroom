from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OpsCertificationRepository:
    db_path: Path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

    def record_chaos_run(
        self,
        *,
        run_id: str,
        scenario: str,
        status: str,
        survivability_score: float,
        detail: dict[str, Any] | None = None,
        ended: bool = False,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_chaos_runs
                (run_id, scenario, status, survivability_score, detail_json, started_at, ended_at)
                VALUES (?, ?, ?, ?, ?, COALESCE(
                    (SELECT started_at FROM ops_chaos_runs WHERE run_id = ?), ?
                ), ?)
                """,
                (
                    run_id,
                    scenario,
                    status,
                    survivability_score,
                    json.dumps(detail or {}),
                    run_id,
                    _utcnow(),
                    _utcnow() if ended else None,
                ),
            )
            conn.commit()

    def latest_chaos_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ops_chaos_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_slo_snapshot(
        self,
        *,
        slo_name: str,
        window_hours: float,
        compliance_ratio: float,
        burn_rate: float,
        error_budget_remaining: float,
        violated: bool,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_slo_snapshots
                (slo_name, window_hours, compliance_ratio, burn_rate,
                 error_budget_remaining, violated, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slo_name,
                    window_hours,
                    compliance_ratio,
                    burn_rate,
                    error_budget_remaining,
                    1 if violated else 0,
                    _utcnow(),
                ),
            )
            conn.commit()

    def slo_history(self, slo_name: str, limit: int = 48) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM ops_slo_snapshots
                WHERE slo_name = ? ORDER BY created_at DESC LIMIT ?
                """,
                (slo_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_certification_state(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_certification_state WHERE id = 1").fetchone()
        return dict(row) if row else None

    def set_certification_state(
        self,
        *,
        state: str,
        score: float,
        blockers: list[str],
        certified: bool = False,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_certification_state
                (id, state, score, blockers_json, certified_at, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    state,
                    score,
                    json.dumps(blockers),
                    _utcnow() if certified else None,
                    _utcnow(),
                ),
            )
            conn.commit()

    def append_audit_chain(
        self,
        *,
        action_id: str,
        operator_id: str,
        command: str,
        payload_hash: str,
        prev_hash: str,
        chain_hash: str,
        signature: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_audit_chain
                (action_id, operator_id, command, payload_hash, prev_hash, chain_hash, signature, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    operator_id,
                    command,
                    payload_hash,
                    prev_hash,
                    chain_hash,
                    signature,
                    _utcnow(),
                ),
            )
            conn.commit()

    def last_audit_hash(self) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT chain_hash FROM ops_audit_chain ORDER BY seq DESC LIMIT 1",
            ).fetchone()
        return row[0] if row else "genesis"

    def audit_entry(self, action_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_audit_chain WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_governance_state(self) -> dict[str, Any]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_governance_state WHERE id = 1").fetchone()
        if row:
            return dict(row)
        default = {
            "id": 1,
            "editorial_frozen": 0,
            "quarantine_depth": 0,
            "consensus_required": 0,
            "sensitive_topics_json": "[]",
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO ops_governance_state
                (id, editorial_frozen, quarantine_depth, consensus_required, sensitive_topics_json, updated_at)
                VALUES (1, 0, 0, 0, '[]', ?)
                """,
                (_utcnow(),),
            )
            conn.commit()
        return default

    def set_governance_state(self, **fields: Any) -> None:
        current = self.get_governance_state()
        current.update(fields)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_governance_state
                (id, editorial_frozen, quarantine_depth, consensus_required, sensitive_topics_json, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    int(current.get("editorial_frozen", 0)),
                    int(current.get("quarantine_depth", 0)),
                    int(current.get("consensus_required", 0)),
                    current.get("sensitive_topics_json", "[]"),
                    _utcnow(),
                ),
            )
            conn.commit()

    def save_executive_report(
        self,
        *,
        report_id: str,
        report_type: str,
        summary: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_executive_reports
                (report_id, report_type, summary_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (report_id, report_type, json.dumps(summary), _utcnow()),
            )
            conn.commit()

    def latest_executive_report(self, report_type: str = "daily") -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM ops_executive_reports
                WHERE report_type = ? ORDER BY created_at DESC LIMIT 1
                """,
                (report_type,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["summary"] = json.loads(out.pop("summary_json", "{}"))
        return out

    def poison_queue_count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM ops_poison_queue").fetchone()
        return int(row[0]) if row else 0
