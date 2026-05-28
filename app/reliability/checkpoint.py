"""Bootstrap pipeline state from checkpoint on startup."""

from __future__ import annotations

import logging
from typing import Any

from ops.pipeline.checkpoint_store import load_checkpoint, save_checkpoint
from ops.resilience.publish_journal import find_inflight

logger = logging.getLogger(__name__)


def bootstrap_runtime_state(settings: Any) -> dict[str, Any]:
    """Load checkpoint, reconcile inflight publish journal entries."""
    rd = str(getattr(settings, "runtime_state_dir", "var/runtime"))
    ckpt = load_checkpoint(rd)
    inflight = find_inflight(rd, max_age_sec=600.0)
    if inflight:
        ckpt["inflight"] = inflight
        logger.warning(
            "checkpoint inflight publish txs=%s (resume without auto-republish)",
            len(inflight),
        )
    save_checkpoint(rd, {"last_stable_state": "bootstrapped", "inflight": inflight})
    return ckpt


def persist_tick_checkpoint(
    settings: Any,
    *,
    tick_id: str,
    publish_outcome: str,
    draft_id: int | None = None,
    idempotency_key: str = "",
) -> None:
    rd = str(getattr(settings, "runtime_state_dir", "var/runtime"))
    patch: dict[str, Any] = {
        "last_tick_id": tick_id,
        "last_stable_state": "tick_completed",
        "last_publish_outcome": publish_outcome,
        "last_draft_id": draft_id,
    }
    if idempotency_key:
        ckpt = load_checkpoint(rd)
        keys = list(ckpt.get("published_idempotency_keys") or [])
        if idempotency_key not in keys:
            keys.append(idempotency_key)
        patch["published_idempotency_keys"] = keys[-500:]
    save_checkpoint(rd, patch)
