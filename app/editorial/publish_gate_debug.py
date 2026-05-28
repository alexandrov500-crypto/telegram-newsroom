"""Structured logging for final publish gate (no silent blocks)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def final_publish_gate_debug_enabled() -> bool:
    return os.getenv("FINAL_PUBLISH_GATE_DEBUG", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def log_gate_decision(
    *,
    draft_id: int | None,
    verdict: Any,
    extra: dict[str, Any] | None = None,
) -> None:
    if not final_publish_gate_debug_enabled():
        return
    payload: dict[str, Any] = {
        "draft_id": draft_id,
        "allowed": getattr(verdict, "allowed", None),
        "reason": getattr(verdict, "reason", ""),
        "manual_review_required": getattr(verdict, "manual_review_required", None),
        "permanent_block": getattr(verdict, "permanent_block", None),
        "trust_score": getattr(verdict, "trust_score", None),
    }
    if extra:
        payload.update(extra)
    logger.info("final_publish_gate.decision %s", json.dumps(payload, ensure_ascii=False, default=str))
