from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_LAG_THRESHOLD = float(os.getenv("SOFT_DEGRADE_LAG_SEC", "2.0"))
_RECOVER_LAG = float(os.getenv("SOFT_DEGRADE_RECOVER_LAG_SEC", "0.75"))
_STALL_WINDOW = int(os.getenv("SOFT_DEGRADE_STALL_COUNT", "2"))
_last_stall_ts: float = 0.0
_consecutive_stalls: int = 0
_last_apply_ts: float = 0.0


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def evaluate_soft_degradation() -> dict[str, Any]:
    """Apply or release soft-degraded mode based on loop lag and stalls."""
    from bot.observability.loop_diagnostics import get_loop_diagnostics
    from bot.observability.loop_health import record_stalled_loops
    from bot.observability.loop_registry import get_loop_registry
    from bot.runtime.state import runtime_state

    diag = get_loop_diagnostics()
    stalled = get_loop_registry().watchdog_stalled_names()
    if stalled:
        record_stalled_loops(stalled)

    global _consecutive_stalls, _last_stall_ts
    now = time.monotonic()
    if stalled:
        if now - _last_stall_ts < 120:
            _consecutive_stalls += 1
        else:
            _consecutive_stalls = 1
        _last_stall_ts = now
    elif now - _last_stall_ts > 300:
        _consecutive_stalls = 0

    should_degrade = (
        diag.event_loop_lag_max >= _LAG_THRESHOLD
        or _consecutive_stalls >= _STALL_WINDOW
    )
    should_recover = (
        runtime_state.soft_degraded
        and diag.last_lag_sec < _RECOVER_LAG
        and not stalled
        and _consecutive_stalls == 0
    )

    changed = False
    if should_degrade and not runtime_state.soft_degraded:
        runtime_state.soft_degraded = True
        runtime_state.ingestion_paused = True
        runtime_state.autonomous_passive = True
        runtime_state.ingestion_interval_multiplier = max(
            runtime_state.ingestion_interval_multiplier,
            float(os.getenv("SOFT_DEGRADE_INGESTION_MULTIPLIER", "3")),
        )
        changed = True
        logger.warning(
            "event=soft_degraded_mode_enabled lag_max=%.3f stalled=%s",
            diag.event_loop_lag_max,
            stalled,
        )
    elif should_recover:
        runtime_state.soft_degraded = False
        runtime_state.ingestion_paused = False
        runtime_state.ingestion_interval_multiplier = 1.0
        changed = True
        logger.info("event=soft_degraded_mode_cleared lag=%.3f", diag.last_lag_sec)

    return {
        "soft_degraded": runtime_state.soft_degraded,
        "ingestion_paused": runtime_state.ingestion_paused,
        "autonomous_passive": runtime_state.autonomous_passive,
        "ingestion_interval_multiplier": runtime_state.ingestion_interval_multiplier,
        "stalled_loops": stalled,
        "consecutive_stall_signals": _consecutive_stalls,
        "changed": changed,
    }
