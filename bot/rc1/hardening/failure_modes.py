from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FailureModeGuard:
    """Detect and remediate: retry storms, DLQ explosions, stale locks, orphan workers."""

    _retry_counts: dict[str, int] = field(default_factory=dict)
    _dlq_window: list[tuple[float, int]] = field(default_factory=list)
    _last_remediation: dict[str, float] = field(default_factory=dict)
    max_retries_per_key: int = 8
    dlq_burst_threshold: int = 50

    def record_retry(self, key: str) -> bool:
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
        if self._retry_counts[key] > self.max_retries_per_key:
            logger.warning("event=retry_amplification key=%s count=%d", key, self._retry_counts[key])
            return True
        return False

    def record_dlq(self, count: int) -> bool:
        now = time.monotonic()
        self._dlq_window.append((now, count))
        self._dlq_window = [(t, c) for t, c in self._dlq_window if now - t < 300]
        if count >= self.dlq_burst_threshold:
            return True
        return False

    def reset_retry(self, key: str) -> None:
        self._retry_counts.pop(key, None)

    def should_block_replay_storm(self, replay_rate: float) -> bool:
        return replay_rate > 100.0

    def remediation_hint(self, issue: str) -> str:
        hints = {
            "retry_amplification": "Pause ingest → inspect DLQ → /recovery_state",
            "dlq_explosion": "/eventbus_live → quarantine poison → RECOVERY_MODE",
            "duplicate_publish": "Verify idempotency cache → /publish_pressure",
            "stale_lock": "Release Redis lock or restart worker role",
            "orphan_worker": "/worker_mesh → restart stale role",
            "stuck_rollout": "/rollout_status → /rollout_rollback",
        }
        return hints.get(issue, "/system_risk")

    def scan(
        self,
        *,
        dlq_count: int = 0,
        queue_depth: int = 0,
        stale_workers: int = 0,
        replay_pending: int = 0,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        if self.record_dlq(dlq_count):
            issues.append({"id": "dlq_explosion", "severity": "critical"})
        if queue_depth > 800:
            issues.append({"id": "queue_runaway", "severity": "error"})
        if stale_workers > 0:
            issues.append({"id": "orphan_worker", "severity": "warn"})
        if replay_pending > 200:
            issues.append({"id": "replay_storm", "severity": "error"})
        for issue in issues:
            issue["remediation"] = self.remediation_hint(issue["id"])
        return issues
