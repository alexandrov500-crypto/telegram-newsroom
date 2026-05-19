from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.workflows.types import WorkflowCheckpoint, WorkflowRun, WorkflowStatus

logger = logging.getLogger(__name__)


class WorkflowCheckpointStore:
    """Resumable workflow state with lease-based ownership."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def start_run(
        self,
        run: WorkflowRun,
        *,
        lease_ttl_sec: int = 300,
    ) -> bool:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lease_ttl_sec)).isoformat()
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT workflow_id, holder_node_id, lease_expires_at FROM workflow_runs WHERE workflow_id = ?",
                (run.workflow_id,),
            ).fetchone()
            if row is not None:
                expired = str(row["lease_expires_at"] or "") < now
                same = str(row["holder_node_id"]) == run.holder_node_id
                if not expired and not same:
                    return False
            conn.execute(
                """
                INSERT INTO workflow_runs (
                    workflow_id, workflow_type, correlation_id, status,
                    holder_node_id, lease_expires_at, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    holder_node_id = excluded.holder_node_id,
                    lease_expires_at = excluded.lease_expires_at,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    run.workflow_id,
                    run.workflow_type,
                    run.correlation_id,
                    WorkflowStatus.RUNNING.value,
                    run.holder_node_id,
                    expires,
                    run.started_at,
                    now,
                ),
            )
            conn.commit()
        return True

    def renew_lease(self, workflow_id: str, *, node_id: str, ttl_sec: int = 300) -> bool:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)).isoformat()
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE workflow_runs
                SET lease_expires_at = ?, updated_at = ?
                WHERE workflow_id = ? AND holder_node_id = ?
                """,
                (expires, now, workflow_id, node_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workflow_checkpoints (
                    workflow_id, step_name, checkpoint_json, sequence_num, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id, step_name) DO UPDATE SET
                    checkpoint_json = excluded.checkpoint_json,
                    sequence_num = excluded.sequence_num,
                    created_at = excluded.created_at
                """,
                (
                    checkpoint.workflow_id,
                    checkpoint.step_name,
                    json.dumps(checkpoint.data),
                    checkpoint.sequence_num,
                    checkpoint.created_at,
                ),
            )
            conn.execute(
                "UPDATE workflow_runs SET updated_at = ? WHERE workflow_id = ?",
                (self._now(), checkpoint.workflow_id),
            )
            conn.commit()

    def get_checkpoint(self, workflow_id: str, step_name: str) -> WorkflowCheckpoint | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT workflow_id, step_name, checkpoint_json, sequence_num, created_at
                FROM workflow_checkpoints
                WHERE workflow_id = ? AND step_name = ?
                """,
                (workflow_id, step_name),
            ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["checkpoint_json"])
        except json.JSONDecodeError:
            data = {}
        return WorkflowCheckpoint(
            workflow_id=str(row["workflow_id"]),
            step_name=str(row["step_name"]),
            data=data,
            sequence_num=int(row["sequence_num"]),
            created_at=str(row["created_at"]),
        )

    def complete(self, workflow_id: str) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE workflow_runs
                SET status = ?, completed_at = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (WorkflowStatus.COMPLETED.value, now, now, workflow_id),
            )
            conn.commit()

    def fail(self, workflow_id: str) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE workflow_runs SET status = ?, updated_at = ?
                WHERE workflow_id = ?
                """,
                (WorkflowStatus.FAILED.value, now, workflow_id),
            )
            conn.commit()

    def list_stalled(self, *, stale_sec: int = 600) -> list[WorkflowRun]:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_sec)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workflow_id, workflow_type, correlation_id, status,
                       holder_node_id, lease_expires_at, started_at, updated_at
                FROM workflow_runs
                WHERE status = 'running' AND updated_at < ?
                """,
                (cutoff,),
            ).fetchall()
        return [
            WorkflowRun(
                workflow_id=str(r["workflow_id"]),
                workflow_type=str(r["workflow_type"]),
                correlation_id=str(r["correlation_id"]),
                status=str(r["status"]),
                holder_node_id=str(r["holder_node_id"]),
                lease_expires_at=r["lease_expires_at"],
                started_at=str(r["started_at"]),
                updated_at=str(r["updated_at"]),
            )
            for r in rows
        ]

    def list_orphaned_leases(self) -> list[WorkflowRun]:
        now = self._now()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workflow_id, workflow_type, correlation_id, status,
                       holder_node_id, lease_expires_at, started_at, updated_at
                FROM workflow_runs
                WHERE status = 'running' AND lease_expires_at < ?
                """,
                (now,),
            ).fetchall()
        return [
            WorkflowRun(
                workflow_id=str(r["workflow_id"]),
                workflow_type=str(r["workflow_type"]),
                correlation_id=str(r["correlation_id"]),
                status=str(r["status"]),
                holder_node_id=str(r["holder_node_id"]),
                lease_expires_at=r["lease_expires_at"],
                started_at=str(r["started_at"]),
                updated_at=str(r["updated_at"]),
            )
            for r in rows
        ]
