from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.learning.types import (
    AgentPerformanceSnapshot,
    DecisionAudit,
    EditorialOutcome,
    LearningScores,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    memory_key: str
    memory_type: str
    title: str
    summary: str | None
    relevance_score: float
    occurrence_count: int
    last_seen_at: str


class LearningRepository:
    """Persistence for adaptive learning, audits, and long-term memory."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_outcome(self, outcome: EditorialOutcome) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO editorial_outcomes (
                    outcome_type, pending_news_id, story_id, signal_id, source,
                    label, score, detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_type,
                    outcome.pending_news_id,
                    outcome.story_id,
                    outcome.signal_id,
                    outcome.source,
                    outcome.label,
                    outcome.score,
                    json.dumps(outcome.detail),
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def record_audit(self, audit: DecisionAudit) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO decision_audits (
                    action, reason_json, scores_json, policy_name,
                    pending_news_id, story_id, signal_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit.action,
                    json.dumps(audit.reason),
                    json.dumps(audit.scores),
                    audit.policy,
                    audit.pending_news_id,
                    audit.story_id,
                    audit.signal_id,
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_recent_audits(self, *, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT action, reason_json, scores_json, policy_name,
                       pending_news_id, created_at
                FROM decision_audits
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_metric(self, key: str, value: float, *, window_hours: int = 168) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_metrics (metric_key, metric_value, window_hours, computed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(metric_key, window_hours) DO UPDATE SET
                    metric_value = excluded.metric_value,
                    computed_at = excluded.computed_at
                """,
                (key, value, window_hours, self._now()),
            )
            conn.commit()

    def get_metric(self, key: str, *, window_hours: int = 168) -> float | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT metric_value FROM learning_metrics
                WHERE metric_key = ? AND window_hours = ?
                """,
                (key, window_hours),
            ).fetchone()
        return float(row["metric_value"]) if row else None

    def save_agent_snapshot(self, snap: AgentPerformanceSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_performance_snapshots (
                    agent_name, accuracy, latency_ms, usefulness,
                    false_positive_rate, escalation_success, publish_success, snapshot_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.agent_name,
                    snap.accuracy,
                    snap.latency_ms,
                    snap.usefulness,
                    snap.false_positive_rate,
                    snap.escalation_success,
                    snap.publish_success,
                    self._now(),
                ),
            )
            conn.commit()

    def latest_agent_snapshots(self) -> list[AgentPerformanceSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_name, accuracy, latency_ms, usefulness,
                       false_positive_rate, escalation_success, publish_success
                FROM agent_performance_snapshots a
                WHERE snapshot_at = (
                    SELECT MAX(snapshot_at) FROM agent_performance_snapshots b
                    WHERE b.agent_name = a.agent_name
                )
                ORDER BY agent_name
                """
            ).fetchall()
        return [
            AgentPerformanceSnapshot(
                agent_name=str(row["agent_name"]),
                accuracy=float(row["accuracy"]),
                latency_ms=float(row["latency_ms"]),
                usefulness=float(row["usefulness"]),
                false_positive_rate=float(row["false_positive_rate"]),
                escalation_success=float(row["escalation_success"]),
                publish_success=float(row["publish_success"]),
            )
            for row in rows
        ]

    def get_policy_json(self, key: str, default: dict) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM policy_state WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return default
        try:
            parsed = json.loads(row["value_json"])
            return parsed if isinstance(parsed, dict) else default
        except json.JSONDecodeError:
            return default

    def set_policy_json(self, key: str, value: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO policy_state (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(value), self._now()),
            )
            conn.commit()

    def get_tuning(self, param_key: str, default: float) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT current_value FROM adaptive_tuning WHERE param_key = ?",
                (param_key,),
            ).fetchone()
        return float(row["current_value"]) if row else default

    def set_tuning(
        self,
        param_key: str,
        *,
        current: float,
        default: float,
        min_value: float,
        max_value: float,
        log_entry: dict | None = None,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT adjustment_log_json FROM adaptive_tuning WHERE param_key = ?",
                (param_key,),
            ).fetchone()
            log: list = []
            if row and row["adjustment_log_json"]:
                try:
                    log = json.loads(row["adjustment_log_json"])
                except json.JSONDecodeError:
                    log = []
            if log_entry:
                log.append(log_entry)
                log = log[-50:]
            conn.execute(
                """
                INSERT INTO adaptive_tuning (
                    param_key, current_value, default_value, min_value, max_value,
                    last_adjusted_at, adjustment_log_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(param_key) DO UPDATE SET
                    current_value = excluded.current_value,
                    last_adjusted_at = excluded.last_adjusted_at,
                    adjustment_log_json = excluded.adjustment_log_json
                """,
                (
                    param_key,
                    current,
                    default,
                    min_value,
                    max_value,
                    self._now(),
                    json.dumps(log),
                ),
            )
            conn.commit()

    def get_source_weight(self, source_name: str) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT dynamic_weight FROM source_dynamic_weights WHERE source_name = ?",
                (source_name,),
            ).fetchone()
        return float(row["dynamic_weight"]) if row else 1.0

    def upsert_source_weight(
        self,
        *,
        source_name: str,
        dynamic_weight: float,
        base_trust: float,
        false_escalation_rate: float,
        reason: str,
    ) -> None:
        weight = max(0.25, min(1.75, dynamic_weight))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_dynamic_weights (
                    source_name, dynamic_weight, base_trust, false_escalation_rate,
                    adjustment_reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    dynamic_weight = excluded.dynamic_weight,
                    false_escalation_rate = excluded.false_escalation_rate,
                    adjustment_reason = excluded.adjustment_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    source_name,
                    weight,
                    base_trust,
                    false_escalation_rate,
                    reason,
                    self._now(),
                ),
            )
            conn.commit()

    def list_source_weights(self, *, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_name, dynamic_weight, base_trust,
                       false_escalation_rate, adjustment_reason, updated_at
                FROM source_dynamic_weights
                ORDER BY ABS(dynamic_weight - 1.0) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_memory(
        self,
        *,
        memory_key: str,
        memory_type: str,
        title: str,
        summary: str | None,
        entities: list[str],
        relevance_boost: float = 0.05,
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, relevance_score, occurrence_count FROM memory_index WHERE memory_key = ?",
                (memory_key,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO memory_index (
                        memory_key, memory_type, title, summary, entities_json,
                        relevance_score, occurrence_count, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        memory_key,
                        memory_type,
                        title,
                        summary,
                        json.dumps(entities),
                        0.5,
                        now,
                        now,
                    ),
                )
            else:
                new_score = min(1.0, float(row["relevance_score"]) + relevance_boost)
                conn.execute(
                    """
                    UPDATE memory_index
                    SET title = ?, summary = ?, entities_json = ?,
                        relevance_score = ?, occurrence_count = occurrence_count + 1,
                        last_seen_at = ?
                    WHERE memory_key = ?
                    """,
                    (
                        title,
                        summary,
                        json.dumps(entities),
                        new_score,
                        now,
                        memory_key,
                    ),
                )
            conn.commit()

    def recall_memory(self, *, query: str, limit: int = 5) -> list[MemoryRecord]:
        tokens = [t.lower() for t in query.split() if len(t) > 3][:6]
        if not tokens:
            return self.top_memory(limit=limit)
        clauses = " OR ".join(["title LIKE ? OR summary LIKE ?"] * len(tokens))
        params: list[object] = []
        for token in tokens:
            pattern = f"%{token}%"
            params.extend([pattern, pattern])
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, memory_key, memory_type, title, summary,
                       relevance_score, occurrence_count, last_seen_at
                FROM memory_index
                WHERE {clauses}
                ORDER BY relevance_score DESC, occurrence_count DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._memory_row(row) for row in rows]

    def top_memory(self, *, limit: int = 8) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, memory_key, memory_type, title, summary,
                       relevance_score, occurrence_count, last_seen_at
                FROM memory_index
                ORDER BY relevance_score DESC, last_seen_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._memory_row(row) for row in rows]

    @staticmethod
    def _memory_row(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row["id"]),
            memory_key=str(row["memory_key"]),
            memory_type=str(row["memory_type"]),
            title=str(row["title"]),
            summary=row["summary"],
            relevance_score=float(row["relevance_score"]),
            occurrence_count=int(row["occurrence_count"]),
            last_seen_at=str(row["last_seen_at"]),
        )

    def count_outcomes_since(self, since_iso: str, *, label: str | None = None) -> int:
        query = "SELECT COUNT(*) AS cnt FROM editorial_outcomes WHERE created_at >= ?"
        params: list[object] = [since_iso]
        if label:
            query += " AND label = ?"
            params.append(label)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row["cnt"]) if row else 0

    def save_replay_run(
        self,
        *,
        run_label: str,
        from_ts: str,
        to_ts: str,
        events_processed: int,
        signals_matched: int,
        policy_name: str | None,
        summary: dict,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO replay_runs (
                    run_label, from_ts, to_ts, events_processed, signals_matched,
                    policy_name, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_label,
                    from_ts,
                    to_ts,
                    events_processed,
                    signals_matched,
                    policy_name,
                    json.dumps(summary),
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_replay_runs(self, *, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, run_label, from_ts, to_ts, events_processed,
                       signals_matched, policy_name, created_at
                FROM replay_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def outcomes_in_window(self, *, hours: int = 168) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT outcome_type, label, score, source, signal_id, story_id
                FROM editorial_outcomes
                WHERE created_at >= ?
                """,
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]
