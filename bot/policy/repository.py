from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from bot.policy.schema import DEFAULT_CLUSTER_POLICY
from bot.policy.types import ClusterPolicyDocument

logger = logging.getLogger(__name__)


class PolicyRepository:
    """Versioned cluster policy storage with audit trail."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_default()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_default(self) -> None:
        active = self.get_active()
        if active is not None:
            return
        self.save(DEFAULT_CLUSTER_POLICY, activate=True)

    def save(self, doc: ClusterPolicyDocument, *, activate: bool = False) -> None:
        now = self._now()
        with self._connect() as conn:
            if activate:
                conn.execute(
                    "UPDATE cluster_policies SET active = 0 WHERE policy_id = ?",
                    (doc.policy_id,),
                )
            conn.execute(
                """
                INSERT INTO cluster_policies (policy_id, version, payload_json, active, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(policy_id, version) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (
                    doc.policy_id,
                    doc.version,
                    json.dumps(doc.to_dict()),
                    1 if activate else 0,
                    now,
                ),
            )
            conn.commit()

    def get_active(self) -> ClusterPolicyDocument | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM cluster_policies
                WHERE active = 1
                ORDER BY version DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        try:
            return ClusterPolicyDocument.from_dict(json.loads(row["payload_json"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.exception("event=policy_parse_failed")
            return None

    def list_versions(self, policy_id: str) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT version FROM cluster_policies WHERE policy_id = ? ORDER BY version DESC",
                (policy_id,),
            ).fetchall()
        return [int(r["version"]) for r in rows]

    def audit(
        self,
        *,
        policy_id: str,
        version: int,
        decision: str,
        action: str,
        reason: str,
        node_id: str | None = None,
        context: dict | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO policy_audit_log (
                    policy_id, version, decision, action, reason, node_id, context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_id,
                    version,
                    decision,
                    action,
                    reason,
                    node_id,
                    json.dumps(context or {}),
                    self._now(),
                ),
            )
            conn.commit()

    def recent_audits(self, *, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT policy_id, version, decision, action, reason, node_id, created_at
                FROM policy_audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
