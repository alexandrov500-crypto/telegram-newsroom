from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpsEvolutionRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def store_memory(
        self,
        *,
        category: str,
        summary: str,
        detail: dict[str, Any],
        confidence: float,
        outcome: str | None = None,
        similarity_key: str | None = None,
    ) -> str:
        mid = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_evolution_memory
                (memory_id, category, summary, detail_json, confidence, outcome,
                 similarity_key, created_at, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    mid,
                    category,
                    summary[:500],
                    json.dumps(detail),
                    confidence,
                    outcome,
                    similarity_key or category,
                    _utcnow(),
                ),
            )
            conn.commit()
        return mid

    def search_memory(
        self,
        *,
        category: str | None = None,
        similarity_key: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            if similarity_key:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_evolution_memory
                    WHERE archived = 0 AND similarity_key = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (similarity_key, limit),
                ).fetchall()
            elif category:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_evolution_memory
                    WHERE archived = 0 AND category = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_evolution_memory
                    WHERE archived = 0 ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def recurring_patterns(self, *, min_count: int = 3) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT similarity_key, category, COUNT(*) AS c,
                       AVG(confidence) AS avg_conf
                FROM ops_evolution_memory
                WHERE archived = 0
                GROUP BY similarity_key, category
                HAVING c >= ?
                ORDER BY c DESC
                LIMIT 15
                """,
                (min_count,),
            ).fetchall()
        return [dict(r) for r in rows]

    def archive_old_memories(self, *, keep_days: int = 90) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE ops_evolution_memory SET archived = 1
                WHERE archived = 0 AND created_at < datetime('now', ?)
                """,
                (f"-{keep_days} days",),
            )
            conn.commit()
            return cur.rowcount

    def save_strategy_proposal(
        self,
        *,
        domain: str,
        title: str,
        impact: float,
        confidence: float,
        tradeoffs: list[str],
        explain: str,
    ) -> str:
        pid = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_evolution_strategy
                (proposal_id, domain, title, impact_estimate, confidence, tradeoffs_json,
                 explain_text, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (pid, domain, title, impact, confidence, json.dumps(tradeoffs), explain, _utcnow()),
            )
            conn.commit()
        return pid

    def pending_strategies(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ops_evolution_strategy WHERE status = 'pending' ORDER BY created_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def save_maturity_snapshot(self, snapshot: dict[str, float], overall: float) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_evolution_maturity (snapshot_json, overall_score, created_at)
                VALUES (?, ?, ?)
                """,
                (json.dumps(snapshot), overall, _utcnow()),
            )
            conn.commit()

    def maturity_history(self, limit: int = 12) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ops_evolution_maturity ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["snapshot"] = json.loads(d.pop("snapshot_json", "{}"))
            out.append(d)
        return out

    def save_analytics_period(
        self,
        *,
        period: str,
        period_key: str,
        metrics: dict[str, Any],
        sustainability: float,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_evolution_analytics
                (period, period_key, metrics_json, sustainability_score, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (period, period_key, json.dumps(metrics), sustainability, _utcnow()),
            )
            conn.commit()

    def save_maintenance_plan(
        self,
        *,
        window_utc: str,
        tasks: list[dict[str, Any]],
        risk_score: float,
    ) -> str:
        plan_id = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_evolution_maintenance
                (plan_id, window_utc, tasks_json, risk_score, status, created_at)
                VALUES (?, ?, ?, ?, 'proposed', ?)
                """,
                (plan_id, window_utc, json.dumps(tasks), risk_score, _utcnow()),
            )
            conn.commit()
        return plan_id

    def latest_maintenance_plan(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_evolution_maintenance ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["tasks"] = json.loads(out.pop("tasks_json", "[]"))
        return out

    def save_evolution_safety(self, risk: float, flags: list[str]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_evolution_safety (evolution_risk, drift_flags_json, created_at)
                VALUES (?, ?, ?)
                """,
                (risk, json.dumps(flags), _utcnow()),
            )
            conn.commit()

    def latest_evolution_safety(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_evolution_safety ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["flags"] = json.loads(out.pop("drift_flags_json", "[]"))
        return out
