from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bot.epistemic.schema import DEFAULT_EPISTEMIC_GOVERNANCE
from bot.epistemic.types import EpistemicGovernanceDocument, EpistemicScore

logger = logging.getLogger(__name__)


class EpistemicRepository:
    """Durable epistemic integrity state."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_governance()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_governance(self) -> None:
        if self.get_active_governance() is not None:
            return
        self.save_governance(DEFAULT_EPISTEMIC_GOVERNANCE, activate=True)

    def save_governance(self, doc: EpistemicGovernanceDocument, *, activate: bool = False) -> None:
        now = self._now()
        with self._connect() as conn:
            if activate:
                conn.execute(
                    "UPDATE epistemic_governance_policies SET active = 0 WHERE policy_id = ?",
                    (doc.policy_id,),
                )
            conn.execute(
                """
                INSERT INTO epistemic_governance_policies (policy_id, version, payload_json, active, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(policy_id, version) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (doc.policy_id, doc.version, json.dumps(doc.to_dict()), 1 if activate else 0, now),
            )
            conn.commit()

    def get_active_governance(self) -> EpistemicGovernanceDocument | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM epistemic_governance_policies
                WHERE active = 1 ORDER BY version DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return EpistemicGovernanceDocument.from_dict(json.loads(row["payload_json"]))

    def save_score(self, score: EpistemicScore) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_scores
                (score_id, subject_type, subject_id, confidence, uncertainty, evidence_depth,
                 contradiction_exposure, source_diversity, replay_stability, explanation, replay_key,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(score_id) DO UPDATE SET
                    confidence = excluded.confidence,
                    uncertainty = excluded.uncertainty,
                    evidence_depth = excluded.evidence_depth,
                    contradiction_exposure = excluded.contradiction_exposure,
                    source_diversity = excluded.source_diversity,
                    replay_stability = excluded.replay_stability,
                    explanation = excluded.explanation,
                    updated_at = excluded.updated_at
                """,
                (
                    score.score_id,
                    score.subject_type,
                    score.subject_id,
                    score.confidence,
                    score.uncertainty,
                    score.evidence_depth,
                    score.contradiction_exposure,
                    score.source_diversity,
                    score.replay_stability,
                    score.explanation,
                    score.replay_key,
                    now,
                    now,
                ),
            )
            conn.commit()

    def get_score(self, subject_type: str, subject_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM epistemic_scores
                WHERE subject_type = ? AND subject_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (subject_type, subject_id),
            ).fetchone()
        return dict(row) if row else None

    def log_confidence_change(
        self,
        score_id: str,
        prior: float,
        posterior: float,
        reason: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_confidence_log
                (score_id, prior_confidence, posterior_confidence, delta_reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (score_id, prior, posterior, reason, self._now()),
            )
            conn.commit()

    def create_contradiction(
        self,
        *,
        cluster_id: str,
        subject_type: str,
        severity: float,
        explanation: str,
        minority_views: list | None = None,
    ) -> str:
        cid = str(uuid.uuid4())[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_contradictions
                (contradiction_id, cluster_id, subject_type, severity, status, explanation,
                 minority_preserved_json, created_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (
                    cid,
                    cluster_id,
                    subject_type,
                    severity,
                    explanation,
                    json.dumps(minority_views or []),
                    self._now(),
                ),
            )
            conn.commit()
        return cid

    def add_contradiction_edge(
        self,
        contradiction_id: str,
        from_claim: str,
        to_claim: str,
        edge_type: str,
        *,
        weight: float = 1.0,
        region: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_contradiction_edges
                (contradiction_id, from_claim, to_claim, edge_type, weight, region, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (contradiction_id, from_claim, to_claim, edge_type, weight, region, self._now()),
            )
            conn.commit()

    def open_contradictions(self, *, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM epistemic_contradictions
                WHERE status = 'open' ORDER BY severity DESC, created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_narrative(
        self,
        narrative_id: str,
        *,
        fingerprint: str,
        topic: str,
        framing: dict,
        region: str | None = None,
        anomaly_score: float = 0.0,
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_narratives
                (narrative_id, fingerprint, topic, region, framing_json, anomaly_score, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(narrative_id) DO UPDATE SET
                    framing_json = excluded.framing_json,
                    anomaly_score = excluded.anomaly_score,
                    updated_at = excluded.updated_at
                """,
                (narrative_id, fingerprint, topic, region, json.dumps(framing), anomaly_score, now, now),
            )
            conn.commit()

    def append_narrative_event(
        self,
        narrative_id: str,
        event_type: str,
        detail: dict,
        *,
        temporal_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_narrative_events
                (narrative_id, event_type, detail_json, temporal_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    narrative_id,
                    event_type,
                    json.dumps(detail),
                    temporal_at or self._now(),
                    self._now(),
                ),
            )
            conn.commit()

    def upsert_trust(
        self,
        from_node: str,
        to_node: str,
        trust: float,
        *,
        reason: str,
        operator_id: str | None = None,
        reversible: bool = True,
    ) -> None:
        prior = self.get_trust(from_node, to_node)
        prior_val = float(prior["trust_score"]) if prior else 0.5
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_trust_edges
                (from_node, to_node, trust_score, reversible, reason, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(from_node, to_node) DO UPDATE SET
                    trust_score = excluded.trust_score,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (from_node, to_node, trust, 1 if reversible else 0, reason, now),
            )
            conn.execute(
                """
                INSERT INTO epistemic_trust_history
                (from_node, to_node, prior_trust, new_trust, action, operator_id, reason, created_at)
                VALUES (?, ?, ?, ?, 'update', ?, ?, ?)
                """,
                (from_node, to_node, prior_val, trust, operator_id, reason, now),
            )
            conn.commit()

    def get_trust(self, from_node: str, to_node: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM epistemic_trust_edges WHERE from_node = ? AND to_node = ?",
                (from_node, to_node),
            ).fetchone()
        return dict(row) if row else None

    def create_alert(
        self,
        *,
        alert_type: str,
        severity: float,
        subject_id: str,
        explanation: str,
        region: str | None = None,
        payload: dict | None = None,
    ) -> str:
        aid = str(uuid.uuid4())[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_alerts
                (alert_id, alert_type, severity, subject_id, explanation, status, region, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending_review', ?, ?, ?)
                """,
                (aid, alert_type, severity, subject_id, explanation, region, json.dumps(payload or {}), self._now()),
            )
            conn.commit()
        return aid

    def validate_alert(self, alert_id: str, *, operator_id: str | None, accepted: bool) -> None:
        status = "validated" if accepted else "rejected"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE epistemic_alerts
                SET status = ?, operator_validated = ?
                WHERE alert_id = ?
                """,
                (status, 1 if accepted else 0, alert_id),
            )
            conn.commit()

    def save_replay_run(
        self,
        run_id: str,
        *,
        subject_type: str,
        subject_id: str,
        stability: float,
        divergence: float,
        detail: dict,
        lane: str = "epistemic",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_replay_runs
                (run_id, lane, subject_type, subject_id, stability_score, divergence_score, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    lane,
                    subject_type,
                    subject_id,
                    stability,
                    divergence,
                    json.dumps(detail),
                    self._now(),
                ),
            )
            conn.commit()

    def record_drift_sample(
        self,
        drift_kind: str,
        *,
        entropy: float,
        diversity: float,
        region: str | None = None,
        detail: dict | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_drift_samples
                (drift_kind, region, entropy_score, diversity_score, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (drift_kind, region, entropy, diversity, json.dumps(detail or {}), self._now()),
            )
            conn.commit()

    def record_calibration(
        self,
        calibration_type: str,
        subject_type: str,
        subject_id: str,
        *,
        operator_id: str | None = None,
        annotation: str | None = None,
        prior: float | None = None,
        new_value: float | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO epistemic_calibration_events
                (calibration_type, subject_type, subject_id, operator_id, annotation,
                 prior_value, new_value, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    calibration_type,
                    subject_type,
                    subject_id,
                    operator_id,
                    annotation,
                    prior,
                    new_value,
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def save_observability_snapshot(self, snapshot_type: str, snapshot: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO epistemic_observability_snapshots (snapshot_type, snapshot_json, created_at)
                VALUES (?, ?, ?)
                """,
                (snapshot_type, json.dumps(snapshot), self._now()),
            )
            conn.commit()

    def latest_snapshot(self, snapshot_type: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT snapshot_json FROM epistemic_observability_snapshots
                WHERE snapshot_type = ? ORDER BY created_at DESC LIMIT 1
                """,
                (snapshot_type,),
            ).fetchone()
        return json.loads(row["snapshot_json"]) if row else None
