from __future__ import annotations

import logging
from typing import Any

from bot.cognitive.learning import LearningCoordinator
from bot.mesh.repository import MeshRepository

logger = logging.getLogger(__name__)


class FederatedLearningMesh:
    """Mesh-scale bounded learning with operator approval gates."""

    def __init__(
        self,
        mesh_repo: MeshRepository,
        local_learning: LearningCoordinator,
        *,
        node_id: str,
        region: str,
        federated_sync: Any | None = None,
    ) -> None:
        self._mesh = mesh_repo
        self._local = local_learning
        self._node_id = node_id
        self._region = region
        self._federated = federated_sync
        self._max_delta = float(local_learning._max_delta)

    def propose_delta(
        self,
        delta_kind: str,
        delta: dict[str, Any],
        *,
        weight: float = 1.0,
        evaluation_score: float | None = None,
    ) -> int:
        if evaluation_score is not None:
            weight *= max(0.1, evaluation_score)
        return self._mesh.record_learning_delta(
            region=self._region,
            node_id=self._node_id,
            delta_kind=delta_kind,
            delta=delta,
            weight=weight,
            approved=False,
        )

    def aggregate_pending(self, *, quorum_fraction: float = 0.51) -> dict[str, Any]:
        pending = self._mesh.pending_learning_deltas(region=self._region)
        if not pending:
            return {"aggregated": 0, "deltas": []}

        by_kind: dict[str, list[dict]] = {}
        for row in pending:
            by_kind.setdefault(row["delta_kind"], []).append(row)

        aggregated: list[dict] = []
        for kind, rows in by_kind.items():
            if len(rows) < 2:
                continue
            merged = self._merge_deltas(kind, rows)
            aggregated.append(merged)

        return {"aggregated": len(aggregated), "deltas": aggregated, "quorum": quorum_fraction}

    def _merge_deltas(self, kind: str, rows: list[dict]) -> dict:
        import json

        total_weight = sum(float(r["weight"]) for r in rows)
        merged_value: dict[str, float] = {}
        for row in rows:
            delta = json.loads(row["delta_json"] or "{}")
            w = float(row["weight"]) / total_weight if total_weight > 0 else 1.0 / len(rows)
            for k, v in delta.items():
                if isinstance(v, (int, float)):
                    merged_value[k] = merged_value.get(k, 0.0) + float(v) * w
        return {
            "kind": kind,
            "merged": merged_value,
            "source_count": len(rows),
            "explanation": f"weighted merge of {len(rows)} regional deltas",
        }

    def apply_approved(self, delta_id: int, *, operator_approved: bool = False) -> bool:
        constitution = self._mesh.get_active_constitution()
        if constitution and constitution.require_operator_for_policy_change and not operator_approved:
            logger.info("event=learning_delta_requires_operator id=%d", delta_id)
            return False
        self._mesh.approve_learning_delta(delta_id)
        return True

    def detect_drift(self, *, baseline: float, current: float, threshold: float = 0.15) -> bool:
        return abs(current - baseline) > threshold

    def sync_to_cluster(self, key: str, payload: dict) -> None:
        if self._federated is not None:
            self._federated.publish(f"mesh_learning_{key}", payload)

    def rollback_mesh(self) -> int:
        return self._local.rollback_last()
