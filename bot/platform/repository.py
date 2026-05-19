from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlatformRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def register_plugin(
        self,
        *,
        plugin_id: str,
        name: str,
        category: str,
        version: str,
        manifest: dict[str, Any],
        capabilities: list[str],
        trust_score: float = 0.5,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO platform_plugins
                (plugin_id, name, category, version, manifest_json, capabilities_json,
                 health_status, enabled, trust_score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'healthy', 1, ?, ?)
                """,
                (
                    plugin_id,
                    name,
                    category,
                    version,
                    json.dumps(manifest),
                    json.dumps(capabilities),
                    trust_score,
                    _utcnow(),
                ),
            )
            conn.commit()

    def list_plugins(self, *, enabled_only: bool = True) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM platform_plugins"
            if enabled_only:
                q += " WHERE enabled = 1"
            q += " ORDER BY category, name"
            rows = conn.execute(q).fetchall()
        return [dict(r) for r in rows]

    def plugin_audit(self, plugin_id: str, action: str, detail: dict[str, Any] | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO platform_plugin_audit (plugin_id, action, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (plugin_id, action, json.dumps(detail or {}), _utcnow()),
            )
            conn.commit()

    def set_plugin_health(self, plugin_id: str, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE platform_plugins SET health_status = ?, updated_at = ? WHERE plugin_id = ?",
                (status, _utcnow(), plugin_id),
            )
            conn.commit()

    def add_graph_edge(
        self,
        *,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        relation: str,
        weight: float = 1.0,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO platform_graph_edges
                (from_type, from_id, to_type, to_id, relation, weight, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (from_type, from_id, to_type, to_id, relation, weight, _utcnow()),
            )
            conn.commit()

    def graph_neighbors(
        self,
        node_type: str,
        node_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM platform_graph_edges
                WHERE from_type = ? AND from_id = ?
                ORDER BY weight DESC LIMIT ?
                """,
                (node_type, node_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_policy(
        self,
        *,
        policy_id: str,
        domain: str,
        version: int,
        policy: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO platform_policies
                (policy_id, domain, version, policy_json, active, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (policy_id, domain, version, json.dumps(policy), _utcnow()),
            )
            conn.commit()

    def active_policies(self, domain: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if domain:
                rows = conn.execute(
                    "SELECT * FROM platform_policies WHERE active = 1 AND domain = ?",
                    (domain,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM platform_policies WHERE active = 1").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["policy"] = json.loads(d.pop("policy_json", "{}"))
            out.append(d)
        return out

    def save_workflow_def(self, name: str, definition: dict[str, Any]) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT version FROM platform_workflow_defs WHERE workflow_name = ?",
                (name,),
            ).fetchone()
            ver = (int(row[0]) + 1) if row else 1
            conn.execute(
                """
                INSERT OR REPLACE INTO platform_workflow_defs
                (workflow_name, definition_json, version, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, json.dumps(definition), ver, _utcnow()),
            )
            conn.commit()

    def get_workflow_def(self, name: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM platform_workflow_defs WHERE workflow_name = ?",
                (name,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["definition"] = json.loads(out.pop("definition_json", "{}"))
        return out

    def workflow_run_status(self, workflow_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_inventory(self, snapshot: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO platform_inventory (id, snapshot_json, updated_at)
                VALUES (1, ?, ?)
                """,
                (json.dumps(snapshot), _utcnow()),
            )
            conn.commit()

    def get_inventory(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT snapshot_json FROM platform_inventory WHERE id = 1").fetchone()
        return json.loads(row["snapshot_json"]) if row else None

    def policy_history(self, domain: str, *, limit: int = 5) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM platform_policies
                WHERE domain = ? ORDER BY version DESC LIMIT ?
                """,
                (domain, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["policy"] = json.loads(d.pop("policy_json", "{}"))
            out.append(d)
        return out

    def graph_edge_count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM platform_graph_edges").fetchone()
        return int(row[0]) if row else 0

    def api_audit(self, endpoint: str, scope: str, caller: str, status: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO platform_api_audit (endpoint, scope, caller, status_code, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (endpoint, scope, caller, status, _utcnow()),
            )
            conn.commit()
