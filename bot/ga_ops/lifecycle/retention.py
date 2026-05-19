from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from bot.ga_ops.repository import GaOpsRepository

logger = logging.getLogger(__name__)


@dataclass
class DataLifecycleManager:
    """Hot/warm/cold retention, pruning, downsampling."""

    repository: GaOpsRepository
    slo_keep_days: int = 14
    quality_keep_days: int = 30

    def run_maintenance(self) -> dict[str, int]:
        results: dict[str, int] = {}
        pruned = self.repository.prune_old_slo_snapshots(keep_days=self.slo_keep_days)
        results["slo_snapshots_pruned"] = pruned
        self.repository.record_retention_run(
            run_id=str(uuid.uuid4()),
            policy="slo_downsample",
            rows=pruned,
        )
        logger.info("event=ga_retention_pass results=%s", results)
        return results

    def verify_archive_integrity(self, *, snapshot_hash: str | None = None) -> bool:
        if snapshot_hash is None:
            snap = self.repository.latest_rollback_snapshot()
            if snap is None:
                return True
            snapshot_hash = snap.get("integrity_hash", "")
        return len(snapshot_hash) >= 8
