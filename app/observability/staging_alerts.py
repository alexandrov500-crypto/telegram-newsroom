"""Emit structured operator alerts from staging health evaluation."""

from __future__ import annotations

import logging

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def log_staging_alerts() -> list[dict]:
    from app.observability.staging_health import staging_health_snapshot

    snap = staging_health_snapshot()
    alerts = list(snap.get("alerts") or [])
    for alert in alerts:
        sev = str(alert.get("severity") or "info")
        code = str(alert.get("code") or "staging.unknown")
        msg = str(alert.get("message") or "")
        log_event(
            logger,
            "ops.staging_alert",
            severity=sev,
            code=code,
            message=msg,
            launch_ready=bool(snap.get("launch_ready")),
        )
        if sev == "critical":
            log_event(logger, "ops.critical", code=code, message=msg)
    return alerts
