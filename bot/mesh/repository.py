from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.mesh.schema import DEFAULT_CONSTITUTION
from bot.mesh.types import ConstitutionalPolicyDocument

logger = logging.getLogger(__name__)


class MeshRepository:
    """Durable mesh state: events, agents, memory, reasoning, governance."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_constitution()
        self._ensure_resilience()
        self._ensure_budget("global")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_constitution(self) -> None:
        if self.get_active_constitution() is not None:
            return
        self.save_constitution(DEFAULT_CONSTITUTION, activate=True)

    def _ensure_resilience(self) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM mesh_resilience_state WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO mesh_resilience_state (id, mesh_health, trust_decay, quarantined_nodes_json, updated_at)
                    VALUES (1, 1.0, 0.0, '[]', ?)
                    """,
                    (self._now(),),
                )
                conn.commit()

    def _ensure_budget(self, region: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT region FROM mesh_cognitive_budgets WHERE region = ?", (region,)
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO mesh_cognitive_budgets
                    (region, reasoning_quota, memory_quota, simulation_quota,
                     spent_reasoning, spent_memory, spent_simulation, updated_at)
                    VALUES (?, 100, 1000, 10, 0, 0, 0, ?)
                    """,
                    (region, self._now()),
                )
                conn.commit()

    def save_constitution(self, doc: ConstitutionalPolicyDocument, *, activate: bool = False) -> None:
        now = self._now()
        with self._connect() as conn:
            if activate:
                conn.execute(
                    "UPDATE mesh_constitutional_policies SET active = 0 WHERE policy_id = ?",
                    (doc.policy_id,),
                )
            conn.execute(
                """
                INSERT INTO mesh_constitutional_policies (policy_id, version, payload_json, active, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(policy_id, version) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (doc.policy_id, doc.version, json.dumps(doc.to_dict()), 1 if activate else 0, now),
            )
            conn.commit()

    def get_active_constitution(self) -> ConstitutionalPolicyDocument | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM mesh_constitutional_policies
                WHERE active = 1 ORDER BY version DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return ConstitutionalPolicyDocument.from_dict(json.loads(row["payload_json"]))

    def record_cognitive_event(
        self,
        *,
        event_id: str,
        event_type: str,
        lane: str,
        region: str,
        origin_node: str,
        payload: dict,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        sequence_num: int = 0,
    ) -> bool:
        """Returns False if duplicate (dedup)."""
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO mesh_cognitive_events
                    (event_id, event_type, lane, region, origin_node, payload_json,
                     causation_id, correlation_id, sequence_num, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        event_type,
                        lane,
                        region,
                        origin_node,
                        json.dumps(payload),
                        causation_id,
                        correlation_id,
                        sequence_num,
                        self._now(),
                    ),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def has_event(self, event_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM mesh_cognitive_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return row is not None

    def recent_events(self, *, region: str | None = None, limit: int = 50) -> list[dict]:
        q = "SELECT * FROM mesh_cognitive_events"
        params: list[object] = []
        if region:
            q += " WHERE region = ?"
            params.append(region)
        q += " ORDER BY sequence_num DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(q, params).fetchall()]

    def next_sequence(self, node_id: str, region: str) -> int:
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_sequence FROM mesh_gossip_state WHERE node_id = ? AND region = ?",
                (node_id, region),
            ).fetchone()
            seq = int(row["last_sequence"]) + 1 if row else 1
            conn.execute(
                """
                INSERT INTO mesh_gossip_state (node_id, region, last_sequence, gossip_budget, updated_at)
                VALUES (?, ?, ?, 50, ?)
                ON CONFLICT(node_id, region) DO UPDATE SET
                    last_sequence = excluded.last_sequence,
                    updated_at = excluded.updated_at
                """,
                (node_id, region, seq, now),
            )
            conn.commit()
            return seq

    def gossip_budget_remaining(self, node_id: str, region: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT gossip_budget FROM mesh_gossip_state WHERE node_id = ? AND region = ?",
                (node_id, region),
            ).fetchone()
        return int(row["gossip_budget"]) if row else 50

    def consume_gossip_budget(self, node_id: str, region: str, count: int = 1) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT gossip_budget FROM mesh_gossip_state WHERE node_id = ? AND region = ?",
                (node_id, region),
            ).fetchone()
            budget = int(row["gossip_budget"]) if row else 50
            new_budget = max(0, budget - count)
            conn.execute(
                """
                UPDATE mesh_gossip_state SET gossip_budget = ?, updated_at = ?
                WHERE node_id = ? AND region = ?
                """,
                (new_budget, self._now(), node_id, region),
            )
            conn.commit()
            return new_budget

    def reset_gossip_budget(self, node_id: str, region: str, budget: int = 50) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mesh_gossip_state (node_id, region, last_sequence, gossip_budget, updated_at)
                VALUES (?, ?, 0, ?, ?)
                ON CONFLICT(node_id, region) DO UPDATE SET gossip_budget = excluded.gossip_budget
                """,
                (node_id, region, budget, self._now()),
            )
            conn.commit()

    def acquire_agent_lease(
        self,
        *,
        lease_id: str,
        agent_id: str,
        holder_node: str,
        region: str,
        capabilities: list[str],
        ttl_sec: int = 300,
    ) -> bool:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=ttl_sec)).isoformat()
        now = self._now()
        with self._connect() as conn:
            conn.execute("DELETE FROM mesh_agent_leases WHERE expires_at < ?", (now,))
            existing = conn.execute(
                "SELECT holder_node FROM mesh_agent_leases WHERE agent_id = ? AND expires_at >= ?",
                (agent_id, now),
            ).fetchone()
            if existing and existing["holder_node"] != holder_node:
                return False
            conn.execute(
                """
                INSERT OR REPLACE INTO mesh_agent_leases
                (lease_id, agent_id, holder_node, region, capabilities_json, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lease_id, agent_id, holder_node, region, json.dumps(capabilities), expires, now),
            )
            conn.commit()
            return True

    def list_agent_leases(self, *, region: str | None = None) -> list[dict]:
        now = self._now()
        q = "SELECT * FROM mesh_agent_leases WHERE expires_at >= ?"
        params: list[object] = [now]
        if region:
            q += " AND region = ?"
            params.append(region)
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["capabilities"] = json.loads(item.pop("capabilities_json") or "[]")
            out.append(item)
        return out

    def upsert_memory_shard(
        self,
        *,
        shard_id: str,
        region: str,
        memory_id: str,
        payload: dict,
        vector_clock: dict[str, int],
        lineage_id: str | None = None,
        node_id: str = "local",
        action: str = "replicate",
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mesh_memory_shards
                (shard_id, region, memory_id, payload_json, vector_clock, lineage_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(shard_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    vector_clock = excluded.vector_clock,
                    updated_at = excluded.updated_at
                """,
                (
                    shard_id,
                    region,
                    memory_id,
                    json.dumps(payload),
                    json.dumps(vector_clock),
                    lineage_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO mesh_memory_lineage (memory_id, shard_id, action, node_id, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory_id, shard_id, action, node_id, json.dumps({"region": region}), now),
            )
            conn.commit()

    def get_memory_shards(self, memory_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM mesh_memory_shards WHERE memory_id = ? ORDER BY updated_at DESC",
                (memory_id,),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            item["vector_clock"] = json.loads(item.pop("vector_clock") or "{}")
            out.append(item)
        return out

    def create_reasoning_session(self, session_id: str, topic: str, region: str, audit: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mesh_reasoning_sessions
                (session_id, topic, region, status, audit_json, created_at)
                VALUES (?, ?, ?, 'open', ?, ?)
                """,
                (session_id, topic, region, json.dumps(audit), self._now()),
            )
            conn.commit()

    def add_consensus_vote(
        self,
        session_id: str,
        *,
        node_id: str,
        vote: float,
        confidence: float,
        reason: str,
        agent_id: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mesh_consensus_votes
                (session_id, node_id, agent_id, vote, confidence, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, node_id, agent_id, vote, confidence, reason, self._now()),
            )
            conn.commit()

    def complete_reasoning_session(
        self,
        session_id: str,
        *,
        consensus_score: float,
        disagreement: list,
        minority: list,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE mesh_reasoning_sessions
                SET status = 'completed', consensus_score = ?, disagreement_json = ?,
                    minority_json = ?, completed_at = ?
                WHERE session_id = ?
                """,
                (
                    consensus_score,
                    json.dumps(disagreement),
                    json.dumps(minority),
                    self._now(),
                    session_id,
                ),
            )
            conn.commit()

    def get_session_votes(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM mesh_consensus_votes WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()]

    def record_learning_delta(
        self,
        *,
        region: str,
        node_id: str,
        delta_kind: str,
        delta: dict,
        weight: float = 1.0,
        approved: bool = False,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO mesh_learning_deltas
                (region, node_id, delta_kind, delta_json, weight, approved, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (region, node_id, delta_kind, json.dumps(delta), weight, 1 if approved else 0, self._now()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def pending_learning_deltas(self, *, region: str | None = None) -> list[dict]:
        q = "SELECT * FROM mesh_learning_deltas WHERE approved = 0"
        params: list[object] = []
        if region:
            q += " AND region = ?"
            params.append(region)
        q += " ORDER BY created_at DESC LIMIT 100"
        with self._connect() as conn:
            rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def approve_learning_delta(self, delta_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE mesh_learning_deltas SET approved = 1 WHERE id = ?", (delta_id,)
            )
            conn.commit()

    def get_resilience(self) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM mesh_resilience_state WHERE id = 1").fetchone()
        if row is None:
            return {"mesh_health": 1.0, "trust_decay": 0.0, "quarantined_nodes": []}
        return {
            "mesh_health": float(row["mesh_health"]),
            "trust_decay": float(row["trust_decay"]),
            "quarantined_nodes": json.loads(row["quarantined_nodes_json"] or "[]"),
        }

    def update_resilience(
        self,
        *,
        mesh_health: float | None = None,
        trust_decay: float | None = None,
        quarantined_nodes: list[str] | None = None,
    ) -> None:
        current = self.get_resilience()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE mesh_resilience_state SET
                    mesh_health = ?, trust_decay = ?, quarantined_nodes_json = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    mesh_health if mesh_health is not None else current["mesh_health"],
                    trust_decay if trust_decay is not None else current["trust_decay"],
                    json.dumps(quarantined_nodes if quarantined_nodes is not None else current["quarantined_nodes"]),
                    self._now(),
                ),
            )
            conn.commit()

    def create_tournament(self, tournament_id: str, scenarios: list[str], *, lane: str = "mesh_shadow") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mesh_simulation_tournaments
                (tournament_id, scenario_set_json, lane, status, created_at)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (tournament_id, json.dumps(scenarios), lane, self._now()),
            )
            conn.commit()

    def complete_tournament(self, tournament_id: str, *, scores: dict, winner: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE mesh_simulation_tournaments
                SET status = 'completed', scores_json = ?, winner = ?, completed_at = ?
                WHERE tournament_id = ?
                """,
                (json.dumps(scores), winner, self._now(), tournament_id),
            )
            conn.commit()

    def get_budget(self, region: str) -> dict:
        self._ensure_budget(region)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM mesh_cognitive_budgets WHERE region = ?", (region,)
            ).fetchone()
        return dict(row) if row else {}

    def spend_budget(self, region: str, *, reasoning: float = 0, memory: float = 0, simulation: float = 0) -> bool:
        b = self.get_budget(region)
        if (
            float(b.get("spent_reasoning", 0)) + reasoning > float(b.get("reasoning_quota", 100))
            or float(b.get("spent_memory", 0)) + memory > float(b.get("memory_quota", 1000))
            or float(b.get("spent_simulation", 0)) + simulation > float(b.get("simulation_quota", 10))
        ):
            return False
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE mesh_cognitive_budgets SET
                    spent_reasoning = spent_reasoning + ?,
                    spent_memory = spent_memory + ?,
                    spent_simulation = spent_simulation + ?,
                    updated_at = ?
                WHERE region = ?
                """,
                (reasoning, memory, simulation, self._now(), region),
            )
            conn.commit()
        return True

    def save_observability_snapshot(self, snapshot_type: str, snapshot: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mesh_observability_snapshots (snapshot_type, snapshot_json, created_at)
                VALUES (?, ?, ?)
                """,
                (snapshot_type, json.dumps(snapshot), self._now()),
            )
            conn.commit()

    def latest_snapshot(self, snapshot_type: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT snapshot_json FROM mesh_observability_snapshots
                WHERE snapshot_type = ? ORDER BY created_at DESC LIMIT 1
                """,
                (snapshot_type,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["snapshot_json"])
