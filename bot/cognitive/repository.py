from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bot.cognitive.schema import DEFAULT_COGNITIVE_POLICY
from bot.cognitive.types import (
    CognitivePolicyDocument,
    EvaluationResult,
    Prediction,
    RouteDecision,
)

logger = logging.getLogger(__name__)


class CognitiveRepository:
    """Durable storage for cognitive runtime artifacts."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_policy()
        self._ensure_budget()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _bucket() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _ensure_policy(self) -> None:
        if self.get_active_policy() is not None:
            return
        self.save_policy(DEFAULT_COGNITIVE_POLICY, activate=True)

    def _ensure_budget(self) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM cost_budget_state WHERE id = 1").fetchone()
            if row is not None:
                return
            conn.execute(
                """
                INSERT INTO cost_budget_state (id, daily_spend_usd, daily_budget_usd, region_budgets_json, updated_at)
                VALUES (1, 0, ?, '{}', ?)
                """,
                (DEFAULT_COGNITIVE_POLICY.cost.get("daily_budget_usd", 25.0), self._now()),
            )
            conn.commit()

    def save_policy(self, doc: CognitivePolicyDocument, *, activate: bool = False) -> None:
        now = self._now()
        with self._connect() as conn:
            if activate:
                conn.execute(
                    "UPDATE cognitive_policies SET active = 0 WHERE policy_id = ?",
                    (doc.policy_id,),
                )
            conn.execute(
                """
                INSERT INTO cognitive_policies (policy_id, version, payload_json, active, updated_at)
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

    def get_active_policy(self) -> CognitivePolicyDocument | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM cognitive_policies
                WHERE active = 1 ORDER BY version DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        try:
            return CognitivePolicyDocument.from_dict(json.loads(row["payload_json"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.exception("event=cognitive_policy_parse_failed")
            return None

    def save_evaluation(self, result: EvaluationResult) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evaluation_results
                (evaluation_id, target_type, target_id, evaluator_name, score,
                 dimensions_json, explanation, trace_id, replay_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.evaluation_id,
                    result.target_type,
                    result.target_id,
                    result.evaluator_name,
                    result.score,
                    json.dumps([d.__dict__ for d in result.dimensions]),
                    result.explanation,
                    result.trace_id,
                    result.replay_key,
                    now,
                ),
            )
            conn.commit()

    def append_evaluation_trace(
        self,
        evaluation_id: str,
        step: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_traces (evaluation_id, step, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (evaluation_id, step, json.dumps(detail or {}), self._now()),
            )
            conn.commit()

    def list_evaluations(
        self,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        q = "SELECT * FROM evaluation_results WHERE 1=1"
        params: list[object] = []
        if target_type:
            q += " AND target_type = ?"
            params.append(target_type)
        if target_id:
            q += " AND target_id = ?"
            params.append(target_id)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def score_trend(self, target_id: str, *, limit: int = 30) -> list[float]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT score FROM evaluation_results
                WHERE target_id = ? ORDER BY created_at DESC LIMIT ?
                """,
                (target_id, limit),
            ).fetchall()
        return [float(r["score"]) for r in reversed(rows)]

    def audit_route(self, decision: RouteDecision, *, node_id: str, context: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_route_audit
                (route_id, operation, model, strategy, qos_class, reason, context_json, node_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.route_id,
                    context.get("operation", "unknown") if context else "unknown",
                    decision.model,
                    decision.strategy,
                    context.get("qos_class") if context else None,
                    decision.reason,
                    json.dumps(context or {}),
                    node_id,
                    self._now(),
                ),
            )
            conn.commit()

    def upsert_memory(
        self,
        *,
        memory_id: str,
        memory_type: str,
        subject_key: str,
        title: str | None,
        payload: dict[str, object],
        region: str | None = None,
    ) -> None:
        now = self._now()
        bucket = self._bucket()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO editorial_memory_entries
                (memory_id, memory_type, subject_key, title, payload_json, temporal_bucket, region, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    title = excluded.title,
                    updated_at = excluded.updated_at
                """,
                (
                    memory_id,
                    memory_type,
                    subject_key,
                    title,
                    json.dumps(payload),
                    bucket,
                    region,
                    now,
                    now,
                ),
            )
            conn.commit()

    def recall_memory(self, query: str, *, limit: int = 8) -> list[dict[str, object]]:
        tokens = [t for t in query.lower().split() if len(t) > 2][:6]
        if not tokens:
            return []
        clauses = " OR ".join("title LIKE ? OR subject_key LIKE ?" for _ in tokens)
        params: list[object] = []
        for t in tokens:
            params.extend([f"%{t}%", f"%{t}%"])
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT memory_id, memory_type, subject_key, title, payload_json, temporal_bucket
                FROM editorial_memory_entries
                WHERE {clauses}
                ORDER BY updated_at DESC LIMIT ?
                """,
                params,
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["payload"] = json.loads(item.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                item["payload"] = {}
            out.append(item)
        return out

    def prune_memory(self, max_entries: int) -> int:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM editorial_memory_entries").fetchone()["c"]
            if count <= max_entries:
                return 0
            excess = count - max_entries
            conn.execute(
                """
                DELETE FROM editorial_memory_entries
                WHERE memory_id IN (
                    SELECT memory_id FROM editorial_memory_entries
                    ORDER BY updated_at ASC LIMIT ?
                )
                """,
                (excess,),
            )
            conn.commit()
            return excess

    def add_graph_edge(
        self,
        from_node: str,
        to_node: str,
        edge_type: str,
        *,
        weight: float = 1.0,
        metadata: dict | None = None,
        temporal_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO intelligence_graph_edges
                (from_node, to_node, edge_type, weight, temporal_at, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    from_node,
                    to_node,
                    edge_type,
                    weight,
                    temporal_at or self._now(),
                    json.dumps(metadata or {}),
                    self._now(),
                ),
            )
            conn.commit()

    def graph_neighbors(self, node_id: str, *, edge_type: str | None = None, limit: int = 50) -> list[dict]:
        q = "SELECT * FROM intelligence_graph_edges WHERE from_node = ? OR to_node = ?"
        params: list[object] = [node_id, node_id]
        if edge_type:
            q += " AND edge_type = ?"
            params.append(edge_type)
        q += " ORDER BY temporal_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(q, params).fetchall()]

    def register_agent(self, agent_id: str, name: str, capabilities: list[str], autonomy_bound: int = 1) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cognitive_agent_registry (agent_id, name, capabilities_json, autonomy_bound, active, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name = excluded.name,
                    capabilities_json = excluded.capabilities_json,
                    autonomy_bound = excluded.autonomy_bound,
                    updated_at = excluded.updated_at
                """,
                (agent_id, name, json.dumps(capabilities), autonomy_bound, self._now()),
            )
            conn.commit()

    def list_agents(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cognitive_agent_registry WHERE active = 1 ORDER BY name"
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json") or "[]")
            out.append(item)
        return out

    def audit_learning(self, kind: str, action: str, reason: str, delta: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_audit_log (learning_kind, action, delta_json, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (kind, action, json.dumps(delta or {}), reason, self._now()),
            )
            conn.commit()

    def get_budget_state(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cost_budget_state WHERE id = 1").fetchone()
        if row is None:
            return {"daily_spend_usd": 0.0, "daily_budget_usd": 25.0}
        return {
            "daily_spend_usd": float(row["daily_spend_usd"]),
            "daily_budget_usd": float(row["daily_budget_usd"]),
        }

    def update_budget_spend(self, delta_usd: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE cost_budget_state
                SET daily_spend_usd = daily_spend_usd + ?, updated_at = ?
                WHERE id = 1
                """,
                (delta_usd, self._now()),
            )
            conn.commit()

    def save_forecast(self, prediction: Prediction) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO predictive_forecasts
                (forecast_type, horizon_minutes, predicted_value, confidence, explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction.forecast_type,
                    prediction.horizon_minutes,
                    prediction.predicted_value,
                    prediction.confidence,
                    prediction.explanation,
                    self._now(),
                ),
            )
            conn.commit()

    def recent_forecasts(self, *, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM predictive_forecasts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_simulation_run(self, scenario: str, *, lane: str = "shadow", seed: int = 42) -> str:
        run_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO simulation_runs (run_id, scenario, lane, status, deterministic_seed, created_at)
                VALUES (?, ?, ?, 'running', ?, ?)
                """,
                (run_id, scenario, lane, seed, self._now()),
            )
            conn.commit()
        return run_id

    def complete_simulation(self, run_id: str, *, status: str, scores: dict[str, float]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE simulation_runs
                SET status = ?, scores_json = ?, completed_at = ?
                WHERE run_id = ?
                """,
                (status, json.dumps(scores), self._now(), run_id),
            )
            conn.commit()

    def record_feedback(
        self,
        *,
        feedback_type: str,
        target_type: str,
        target_id: str,
        operator_id: str | None = None,
        annotation: str | None = None,
        rating: float | None = None,
        payload: dict | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO operator_feedback_events
                (feedback_type, target_type, target_id, operator_id, annotation, rating, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_type,
                    target_type,
                    target_id,
                    operator_id,
                    annotation,
                    rating,
                    json.dumps(payload or {}),
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def cognitive_audit(self, action: str, reason: str, *, node_id: str, context: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cognitive_audit_log (action, reason, context_json, node_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action, reason, json.dumps(context or {}), node_id, self._now()),
            )
            conn.commit()

    def recent_cognitive_audit(self, *, limit: int = 15) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cognitive_audit_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
