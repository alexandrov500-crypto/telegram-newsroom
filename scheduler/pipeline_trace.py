"""Structured end-to-end pipeline trace for debug publication modes."""

from __future__ import annotations

import logging
from typing import Any

from app.runtime_lifecycle import runtime_id
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def log_pipeline_trace(
    log: logging.Logger,
    *,
    stage: str,
    cluster_id: str | None = None,
    decision: str | None = None,
    reason: str | None = None,
    policy_matches: list[str] | None = None,
    ai_status: str | None = None,
    publish_result: str | None = None,
    draft_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "runtime_id": runtime_id(),
        "stage": stage,
    }
    if cluster_id:
        payload["cluster_id"] = cluster_id
    if decision:
        payload["decision"] = decision
    if reason:
        payload["reason"] = reason
    if policy_matches:
        payload["policy_matches"] = policy_matches[:24]
    if ai_status:
        payload["ai_status"] = ai_status
    if publish_result:
        payload["publish_result"] = publish_result
    if draft_id is not None:
        payload["draft_id"] = draft_id
    if extra:
        payload.update(extra)
    log_event(log, "pipeline.trace", **payload)
