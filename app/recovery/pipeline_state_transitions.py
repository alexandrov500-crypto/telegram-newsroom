"""Log every ai_pipeline_enabled transition (incident visibility)."""

from __future__ import annotations

import logging

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def set_ai_pipeline_enabled(
    value: bool,
    *,
    source: str,
    reason: str = "",
    summarize_enabled: bool | None = None,
) -> bool:
    """
    Set runtime flag and emit PIPELINE_STATE_TRANSITIONS_LOG when value changes.
    Returns True if the value changed.
    """
    from app.dependency_state import get_dependency_state

    deps = get_dependency_state()
    prev = bool(deps.ai_pipeline_enabled)
    if prev == value:
        return False
    deps.ai_pipeline_enabled = value
    log_event(
        logger,
        "PIPELINE_STATE_TRANSITIONS_LOG",
        field="ai_pipeline_enabled",
        from_state=prev,
        to_state=value,
        source=source,
        reason=reason[:300] if reason else "",
        summarize_enabled=summarize_enabled if summarize_enabled is not None else value,
    )
    return True
