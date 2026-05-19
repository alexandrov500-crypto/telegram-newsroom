from __future__ import annotations

import logging
from typing import Any

from bot.storage.coordination_repository import CoordinationRepository

logger = logging.getLogger(__name__)

_SYNC_SOURCE_WEIGHTS = "source_weights"
_SYNC_CREDIBILITY = "credibility_drift"
_SYNC_PRECISION = "signal_precision"
_SYNC_POLICY = "policy_tuning"
_SYNC_ANOMALY = "anomaly_baselines"


class FederatedLearningSync:
    """Bounded cluster-wide learning state (eventual consistency)."""

    def __init__(self, repo: CoordinationRepository, *, max_keys: int = 32) -> None:
        self._repo = repo
        self._max_keys = max_keys

    def publish(self, sync_key: str, payload: dict[str, Any]) -> int:
        bounded = dict(list(payload.items())[:50])
        version = self._repo.upsert_federated_sync(sync_key, bounded)
        logger.info("event=federated_learning_sync key=%s version=%d", sync_key, version)
        return version

    def fetch(self, sync_key: str) -> dict[str, Any] | None:
        row = self._repo.get_federated_sync(sync_key)
        if row is None:
            return None
        return row.get("payload")

    def sync_source_weights(self, weights: dict[str, float]) -> int:
        return self.publish(_SYNC_SOURCE_WEIGHTS, {"weights": weights})

    def sync_credibility_drift(self, drift: dict[str, float]) -> int:
        return self.publish(_SYNC_CREDIBILITY, {"drift": drift})

    def sync_signal_precision(self, precision: dict[str, float]) -> int:
        return self.publish(_SYNC_PRECISION, {"precision": precision})

    def sync_policy_tuning(self, tuning: dict[str, Any]) -> int:
        return self.publish(_SYNC_POLICY, tuning)

    def sync_anomaly_baselines(self, baselines: dict[str, float]) -> int:
        return self.publish(_SYNC_ANOMALY, {"baselines": baselines})

    def merge_source_weights(
        self,
        local: dict[str, float],
        *,
        alpha: float = 0.3,
    ) -> dict[str, float]:
        remote_row = self._repo.get_federated_sync(_SYNC_SOURCE_WEIGHTS)
        if remote_row is None:
            return local
        remote = remote_row.get("payload", {}).get("weights", {})
        merged = dict(local)
        for key, value in remote.items():
            if key in merged:
                merged[key] = (1 - alpha) * merged[key] + alpha * float(value)
            else:
                merged[key] = float(value)
        return merged
