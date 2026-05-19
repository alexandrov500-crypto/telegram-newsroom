from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.storage.db import default_db_path, init_database


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ForensicsRepository:
    """Append-only operational forensics persistence."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or default_db_path()
        init_database(self._db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def append_timeline(
        self,
        *,
        event_type: str,
        severity: str = "info",
        details: dict[str, Any],
        correlation_id: str | None = None,
        publish_id: str | int | None = None,
        timestamp: str | None = None,
        runtime_instance_id: str | None = None,
    ) -> int:
        ts = timestamp or _utcnow()
        if runtime_instance_id is None:
            try:
                from bot.runtime.instance import get_runtime_identity

                ident = get_runtime_identity()
                if ident is not None:
                    runtime_instance_id = ident.runtime_instance_id
            except Exception:
                pass
        pub = str(publish_id) if publish_id is not None else None
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO live_incident_timeline
                (timestamp, runtime_instance_id, event_type, severity,
                 correlation_id, publish_id, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    runtime_instance_id,
                    event_type,
                    severity,
                    correlation_id,
                    pub,
                    json.dumps(details, default=str),
                    _utcnow(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def append_audit(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        actor: str | None = None,
        correlation_id: str | None = None,
        publish_id: str | int | None = None,
        audit_id: str | None = None,
    ) -> str:
        aid = audit_id or f"aud_{uuid.uuid4().hex}"
        ts = _utcnow()
        runtime_instance_id = None
        try:
            from bot.runtime.instance import get_runtime_identity

            ident = get_runtime_identity()
            if ident is not None:
                runtime_instance_id = ident.runtime_instance_id
        except Exception:
            pass
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO live_operational_audit
                (audit_id, timestamp, action, actor, runtime_instance_id,
                 correlation_id, publish_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    ts,
                    action,
                    actor,
                    runtime_instance_id,
                    correlation_id,
                    str(publish_id) if publish_id is not None else None,
                    json.dumps(payload, default=str),
                    ts,
                ),
            )
            conn.commit()
        return aid

    def save_runtime_snapshot(self, snapshot: dict[str, Any]) -> int:
        ts = snapshot.get("timestamp") or _utcnow()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO runtime_state_snapshot
                (timestamp, runtime_instance_id, runtime_profile, snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    snapshot.get("runtime_instance_id"),
                    snapshot.get("runtime_profile"),
                    json.dumps(snapshot, default=str),
                    _utcnow(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def lock_baseline(self, baseline: dict[str, Any], *, notes: str = "") -> None:
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_runtime_baseline (id, locked_at, baseline_json, notes, updated_at)
                VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    locked_at = excluded.locked_at,
                    baseline_json = excluded.baseline_json,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (now, json.dumps(baseline, default=str), notes, now),
            )
            conn.commit()

    def get_baseline(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT baseline_json, locked_at, notes FROM ops_runtime_baseline WHERE id = 1",
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["baseline_json"])
        except json.JSONDecodeError:
            data = {}
        data["_locked_at"] = row["locked_at"]
        data["_notes"] = row["notes"]
        return data

    def query_timeline(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        event_type: str | None = None,
        correlation_id: str | None = None,
        publish_id: str | int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp <= ?")
            params.append(until)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if correlation_id:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if publish_id is not None:
            clauses.append("publish_id = ?")
            params.append(str(publish_id))
        params.append(limit)
        sql = f"""
            SELECT timestamp, runtime_instance_id, event_type, severity,
                   correlation_id, publish_id, details_json
            FROM live_incident_timeline
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp ASC
            LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                details = json.loads(row["details_json"])
            except json.JSONDecodeError:
                details = {"raw": row["details_json"]}
            out.append(
                {
                    "timestamp": row["timestamp"],
                    "runtime_instance_id": row["runtime_instance_id"],
                    "event_type": row["event_type"],
                    "severity": row["severity"],
                    "correlation_id": row["correlation_id"],
                    "publish_id": row["publish_id"],
                    "details": details,
                },
            )
        return out

    def query_audit(
        self,
        *,
        publish_id: str | int | None = None,
        correlation_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if publish_id is not None:
            clauses.append("publish_id = ?")
            params.append(str(publish_id))
        if correlation_id:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        params.append(limit)
        sql = f"""
            SELECT audit_id, timestamp, action, actor, runtime_instance_id,
                   correlation_id, publish_id, payload_json
            FROM live_operational_audit
            WHERE {' AND '.join(clauses)}
            ORDER BY timestamp ASC
            LIMIT ?
        """
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = {}
            result.append(
                {
                    "audit_id": row["audit_id"],
                    "timestamp": row["timestamp"],
                    "action": row["action"],
                    "actor": row["actor"],
                    "runtime_instance_id": row["runtime_instance_id"],
                    "correlation_id": row["correlation_id"],
                    "publish_id": row["publish_id"],
                    "payload": payload,
                },
            )
        return result

    def register_bundle(
        self,
        *,
        bundle_id: str,
        incident_id: str,
        export_path: str,
        summary: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_incident_bundle (bundle_id, incident_id, export_path, summary_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(bundle_id) DO UPDATE SET
                    export_path = excluded.export_path,
                    summary_json = excluded.summary_json
                """,
                (
                    bundle_id,
                    incident_id,
                    export_path,
                    json.dumps(summary, default=str),
                    _utcnow(),
                ),
            )
            conn.commit()

    def prune_old_rows(self, *, table: str, days: int) -> int:
        allowed = {
            "live_incident_timeline",
            "runtime_state_snapshot",
            "live_metrics_snapshots",
        }
        if table not in allowed:
            raise ValueError(f"prune not allowed for {table}")
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM {table} WHERE created_at < datetime('now', ?)",
                (f"-{days} days",),
            )
            conn.commit()
            return int(cur.rowcount or 0)
