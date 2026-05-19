from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from bot.distributed.types import ClusterNodeRecord, StoryVersionVector
from utils.database_url import alembic_sync_url_from_async, is_postgresql_async_url

logger = logging.getLogger(__name__)

_CLUSTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS cluster_nodes (
    node_id TEXT NOT NULL,
    role TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'global',
    status TEXT NOT NULL DEFAULT 'starting',
    is_leader INTEGER NOT NULL DEFAULT 0,
    last_heartbeat_at TEXT NOT NULL,
    started_at TEXT NOT NULL,
    metadata_json TEXT,
    PRIMARY KEY (node_id, role)
);
CREATE TABLE IF NOT EXISTS cluster_leases (
    lease_name TEXT PRIMARY KEY,
    holder_node_id TEXT NOT NULL,
    holder_role TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    fencing_token INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cluster_job_leases (
    job_name TEXT PRIMARY KEY,
    holder_node_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cluster_partitions (
    partition_key TEXT PRIMARY KEY,
    assigned_node_id TEXT,
    paused INTEGER NOT NULL DEFAULT 0,
    lag_events INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS story_federation (
    story_id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    origin_node_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_hash TEXT
);
CREATE TABLE IF NOT EXISTS federated_learning_sync (
    sync_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class LeaseRecord:
    lease_name: str
    holder_node_id: str
    holder_role: str
    expires_at: str
    fencing_token: int


def _row_val(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[key]


class CoordinationRepository:
    """Distributed cluster coordination (SQLite dev / PostgreSQL production)."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        database_url: str | None = None,
    ) -> None:
        self._db_path = db_path
        self._pg_dsn: str | None = None
        if database_url and is_postgresql_async_url(database_url):
            self._pg_dsn = alembic_sync_url_from_async(database_url)
        elif db_path is None:
            raise ValueError("db_path or database_url required")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._connection() as conn:
            if self._pg_dsn:
                for stmt in _CLUSTER_SCHEMA.strip().split(";"):
                    text = stmt.strip()
                    if text:
                        conn.execute(text)
            else:
                conn.executescript(_CLUSTER_SCHEMA)

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if self._pg_dsn:
            import psycopg
            from psycopg.rows import dict_row

            with psycopg.connect(self._pg_dsn, row_factory=dict_row) as conn:
                yield conn
                conn.commit()
            return
        assert self._db_path is not None
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _execute(self, conn: Any, sql: str, params: tuple = ()) -> Any:
        if self._pg_dsn:
            return conn.execute(sql.replace("?", "%s"), params)
        return conn.execute(sql, params)

    def _changes(self, conn: Any, cur: Any) -> int:
        if self._pg_dsn:
            return int(cur.rowcount)
        return int(conn.total_changes)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _expires_in(seconds: int) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def register_node(
        self,
        *,
        node_id: str,
        role: str,
        region: str,
        status: str = "healthy",
        metadata: dict | None = None,
    ) -> None:
        now = self._now()
        with self._connection() as conn:
            self._execute(
                conn,
                """
                INSERT INTO cluster_nodes (
                    node_id, role, region, status, is_leader, last_heartbeat_at,
                    started_at, metadata_json
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(node_id, role) DO UPDATE SET
                    region = excluded.region,
                    status = excluded.status,
                    last_heartbeat_at = excluded.last_heartbeat_at,
                    metadata_json = excluded.metadata_json
                """,
                (node_id, role, region, status, now, now, json.dumps(metadata or {})),
            )

    def heartbeat(self, *, node_id: str, role: str, status: str = "healthy") -> None:
        with self._connection() as conn:
            self._execute(
                conn,
                """
                UPDATE cluster_nodes
                SET last_heartbeat_at = ?, status = ?
                WHERE node_id = ? AND role = ?
                """,
                (self._now(), status, node_id, role),
            )

    def set_node_status(self, *, node_id: str, role: str, status: str) -> None:
        with self._connection() as conn:
            self._execute(
                conn,
                """
                UPDATE cluster_nodes SET status = ?, last_heartbeat_at = ?
                WHERE node_id = ? AND role = ?
                """,
                (status, self._now(), node_id, role),
            )

    def list_nodes(self, *, include_stale: bool = False) -> list[ClusterNodeRecord]:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
        with self._connection() as conn:
            if include_stale:
                cur = self._execute(
                    conn,
                    "SELECT * FROM cluster_nodes ORDER BY last_heartbeat_at DESC",
                )
            else:
                cur = self._execute(
                    conn,
                    """
                    SELECT * FROM cluster_nodes
                    WHERE last_heartbeat_at >= ?
                    ORDER BY last_heartbeat_at DESC
                    """,
                    (cutoff,),
                )
            rows = cur.fetchall()
        return [
            ClusterNodeRecord(
                node_id=str(_row_val(row, "node_id")),
                role=str(_row_val(row, "role")),
                region=str(_row_val(row, "region")),
                status=str(_row_val(row, "status")),
                is_leader=bool(_row_val(row, "is_leader")),
                last_heartbeat_at=str(_row_val(row, "last_heartbeat_at")),
                metadata_json=_row_val(row, "metadata_json"),
            )
            for row in rows
        ]

    def mark_offline_stale(self, *, stale_sec: int = 120) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_sec)).isoformat()
        with self._connection() as conn:
            cur = self._execute(
                conn,
                """
                UPDATE cluster_nodes SET status = 'offline', is_leader = 0
                WHERE last_heartbeat_at < ? AND status != 'offline'
                """,
                (cutoff,),
            )
            return self._changes(conn, cur)

    def try_acquire_lease(
        self,
        lease_name: str,
        *,
        node_id: str,
        role: str,
        ttl_sec: int = 30,
    ) -> LeaseRecord | None:
        now = self._now()
        expires = self._expires_in(ttl_sec)
        with self._connection() as conn:
            cur = self._execute(
                conn,
                "SELECT * FROM cluster_leases WHERE lease_name = ?",
                (lease_name,),
            )
            row = cur.fetchone()
            if row is None:
                self._execute(
                    conn,
                    """
                    INSERT INTO cluster_leases (
                        lease_name, holder_node_id, holder_role, expires_at, fencing_token
                    ) VALUES (?, ?, ?, ?, 1)
                    """,
                    (lease_name, node_id, role, expires),
                )
                return LeaseRecord(lease_name, node_id, role, expires, 1)

            expired = str(_row_val(row, "expires_at")) < now
            same_holder = str(_row_val(row, "holder_node_id")) == node_id
            if expired or same_holder:
                token = int(_row_val(row, "fencing_token")) + (0 if same_holder else 1)
                cur = self._execute(
                    conn,
                    """
                    UPDATE cluster_leases
                    SET holder_node_id = ?, holder_role = ?, expires_at = ?, fencing_token = ?
                    WHERE lease_name = ? AND (expires_at < ? OR holder_node_id = ?)
                    """,
                    (node_id, role, expires, token, lease_name, now, node_id),
                )
                if self._changes(conn, cur) == 0:
                    return None
                return LeaseRecord(lease_name, node_id, role, expires, token)
        return None

    def release_lease(self, lease_name: str, *, node_id: str) -> bool:
        with self._connection() as conn:
            cur = self._execute(
                conn,
                "DELETE FROM cluster_leases WHERE lease_name = ? AND holder_node_id = ?",
                (lease_name, node_id),
            )
            return self._changes(conn, cur) > 0

    def current_leader(self, lease_name: str = "cluster_leader") -> str | None:
        now = self._now()
        with self._connection() as conn:
            cur = self._execute(
                conn,
                """
                SELECT holder_node_id FROM cluster_leases
                WHERE lease_name = ? AND expires_at >= ?
                """,
                (lease_name, now),
            )
            row = cur.fetchone()
        return str(_row_val(row, "holder_node_id")) if row else None

    def release_job(self, job_name: str, *, node_id: str) -> bool:
        with self._connection() as conn:
            cur = self._execute(
                conn,
                "DELETE FROM cluster_job_leases WHERE job_name = ? AND holder_node_id = ?",
                (job_name, node_id),
            )
            return self._changes(conn, cur) > 0

    def try_acquire_job(self, job_name: str, *, node_id: str, ttl_sec: int = 120) -> bool:
        now = self._now()
        expires = self._expires_in(ttl_sec)
        with self._connection() as conn:
            cur = self._execute(
                conn,
                "SELECT holder_node_id, expires_at FROM cluster_job_leases WHERE job_name = ?",
                (job_name,),
            )
            row = cur.fetchone()
            if row is None:
                self._execute(
                    conn,
                    """
                    INSERT INTO cluster_job_leases (job_name, holder_node_id, acquired_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (job_name, node_id, now, expires),
                )
                return True
            if str(_row_val(row, "expires_at")) < now or str(_row_val(row, "holder_node_id")) == node_id:
                cur = self._execute(
                    conn,
                    """
                    UPDATE cluster_job_leases
                    SET holder_node_id = ?, acquired_at = ?, expires_at = ?
                    WHERE job_name = ? AND (expires_at < ? OR holder_node_id = ?)
                    """,
                    (node_id, now, expires, job_name, now, node_id),
                )
                return self._changes(conn, cur) > 0
        return False

    def assign_partition(self, partition_key: str, node_id: str | None) -> None:
        with self._connection() as conn:
            self._execute(
                conn,
                """
                INSERT INTO cluster_partitions (partition_key, assigned_node_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(partition_key) DO UPDATE SET
                    assigned_node_id = excluded.assigned_node_id,
                    updated_at = excluded.updated_at
                """,
                (partition_key, node_id, self._now()),
            )

    def list_partitions(self) -> list[dict]:
        with self._connection() as conn:
            cur = self._execute(
                conn,
                """
                SELECT partition_key, assigned_node_id, paused, lag_events, updated_at
                FROM cluster_partitions
                """,
            )
            rows = cur.fetchall()
        return [{k: _row_val(row, k) for k in (
            "partition_key", "assigned_node_id", "paused", "lag_events", "updated_at"
        )} for row in rows]

    def set_partition_paused(self, partition_key: str, paused: bool) -> None:
        with self._connection() as conn:
            self._execute(
                conn,
                """
                UPDATE cluster_partitions SET paused = ?, updated_at = ?
                WHERE partition_key = ?
                """,
                (1 if paused else 0, self._now(), partition_key),
            )

    def get_story_version(self, story_id: int) -> StoryVersionVector | None:
        with self._connection() as conn:
            cur = self._execute(
                conn,
                """
                SELECT story_id, version, origin_node_id, updated_at
                FROM story_federation WHERE story_id = ?
                """,
                (story_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return StoryVersionVector(
            story_id=int(_row_val(row, "story_id")),
            version=int(_row_val(row, "version")),
            node_id=str(_row_val(row, "origin_node_id")),
            updated_at=str(_row_val(row, "updated_at")),
        )

    def upsert_story_version(
        self,
        *,
        story_id: int,
        node_id: str,
        expected_version: int | None,
        payload_hash: str | None = None,
    ) -> StoryVersionVector | None:
        now = self._now()
        with self._connection() as conn:
            cur = self._execute(
                conn,
                "SELECT version FROM story_federation WHERE story_id = ?",
                (story_id,),
            )
            row = cur.fetchone()
            if row is None:
                version = 1
                self._execute(
                    conn,
                    """
                    INSERT INTO story_federation (
                        story_id, version, origin_node_id, updated_at, payload_hash
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (story_id, version, node_id, now, payload_hash),
                )
                return StoryVersionVector(story_id, version, node_id, now)

            current = int(_row_val(row, "version"))
            if expected_version is not None and expected_version != current:
                return None
            new_version = current + 1
            cur = self._execute(
                conn,
                """
                UPDATE story_federation
                SET version = ?, origin_node_id = ?, updated_at = ?, payload_hash = ?
                WHERE story_id = ? AND version = ?
                """,
                (new_version, node_id, now, payload_hash, story_id, current),
            )
            if self._changes(conn, cur) == 0:
                return None
            return StoryVersionVector(story_id, new_version, node_id, now)

    def upsert_federated_sync(self, sync_key: str, payload: dict) -> int:
        with self._connection() as conn:
            cur = self._execute(
                conn,
                "SELECT version FROM federated_learning_sync WHERE sync_key = ?",
                (sync_key,),
            )
            row = cur.fetchone()
            version = int(_row_val(row, "version")) + 1 if row else 1
            self._execute(
                conn,
                """
                INSERT INTO federated_learning_sync (sync_key, payload_json, version, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sync_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    version = excluded.version,
                    updated_at = excluded.updated_at
                """,
                (sync_key, json.dumps(payload), version, self._now()),
            )
            return version

    def get_federated_sync(self, sync_key: str) -> dict | None:
        with self._connection() as conn:
            cur = self._execute(
                conn,
                """
                SELECT payload_json, version, updated_at
                FROM federated_learning_sync WHERE sync_key = ?
                """,
                (sync_key,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(_row_val(row, "payload_json"))
        except json.JSONDecodeError:
            payload = {}
        return {
            "payload": payload,
            "version": int(_row_val(row, "version")),
            "updated_at": str(_row_val(row, "updated_at")),
        }
