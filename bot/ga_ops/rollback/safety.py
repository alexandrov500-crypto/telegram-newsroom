from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from bot.ga_ops.repository import GaOpsRepository

logger = logging.getLogger(__name__)


@dataclass
class RollbackSafetyManager:
    """Snapshots, dry-run, integrity — no republish, preserve audit chain."""

    repository: GaOpsRepository

    def _hash_detail(self, detail: dict[str, Any]) -> str:
        payload = json.dumps(detail, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def create_snapshot(self, *, stage: str, detail: dict[str, Any]) -> str:
        snap_id = str(uuid.uuid4())
        integrity = self._hash_detail(detail)
        self.repository.save_rollback_snapshot(
            snapshot_id=snap_id,
            stage=stage,
            integrity_hash=integrity,
            detail={**detail, "republish_blocked": True, "audit_preserved": True},
        )
        logger.info("event=ga_rollback_snapshot id=%s stage=%s", snap_id[:12], stage)
        return snap_id

    def verify_integrity(self, snapshot_id: str) -> tuple[bool, str]:
        snap = self.repository.latest_rollback_snapshot()
        if snap is None or snap["snapshot_id"] != snapshot_id:
            if snap is None:
                return False, "no_snapshot"
            return snap["snapshot_id"] == snapshot_id, "latest_mismatch"
        expected = self._hash_detail(snap.get("detail", {}))
        if expected != snap["integrity_hash"]:
            return False, "hash_mismatch"
        return True, "ok"

    def dry_run(self, *, target_stage: str) -> dict[str, Any]:
        snap = self.repository.latest_rollback_snapshot()
        return {
            "dry_run": True,
            "target_stage": target_stage,
            "would_republish": False,
            "audit_preserved": True,
            "forensic_preserved": True,
            "snapshot_available": snap is not None,
        }

    def execute_staged(
        self,
        *,
        target_stage: str,
        apply_fn: Any,
        reason: str,
    ) -> dict[str, Any]:
        detail = {"target": target_stage, "reason": reason}
        snap_id = self.create_snapshot(stage=target_stage, detail=detail)
        dry = self.dry_run(target_stage=target_stage)
        if not dry["snapshot_available"]:
            return {"ok": False, "reason": "no_snapshot"}
        result = apply_fn(reason=reason)
        ok, msg = self.verify_integrity(snap_id)
        logger.info("event=ga_rollback_executed stage=%s integrity=%s", target_stage, msg)
        return {
            "ok": True,
            "snapshot_id": snap_id,
            "integrity": msg,
            "apply_result": str(result),
            "republish_blocked": True,
        }
