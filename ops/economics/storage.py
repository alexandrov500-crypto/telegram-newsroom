"""Storage budgeting, pressure warnings, emergency cleanup hints."""

from __future__ import annotations

import os
import time
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.economics.paths import storage_state_path
from ops.economics.resource_accounting import snapshot_storage_bytes
from utils.structured_log import log_event

logger = __import__("logging").getLogger(__name__)


def _quota_bytes() -> int:
    return int(os.getenv("RUNTIME_STORAGE_QUOTA_BYTES", str(2_000_000_000)))


def assess_storage(runtime_dir: str, *, logger_obj: Any = None) -> dict[str, Any]:
    breakdown = snapshot_storage_bytes(runtime_dir)
    total = int(breakdown.get("total_estimated") or 0)
    quota = _quota_bytes()
    ratio = round(total / max(1, quota), 4)
    pressure = ratio >= 0.75
    emergency = ratio >= 0.92
    warnings: list[str] = []
    if ratio >= 0.75:
        warnings.append("storage_above_75pct_quota")
    if ratio >= 0.92:
        warnings.append("storage_emergency_threshold")
    if breakdown.get("incidents", 0) > quota * 0.4:
        warnings.append("incident_storage_dominant")
    state = {
        "version": 1,
        "assessed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_bytes": total,
        "quota_bytes": quota,
        "usage_ratio": ratio,
        "breakdown": breakdown,
        "pressure": pressure,
        "emergency_cleanup_recommended": emergency,
        "warnings": warnings,
    }
    save_json(storage_state_path(runtime_dir), state)
    log = logger_obj or logger
    if pressure:
        log_event(
            log,
            "storage.pressure.warning",
            usage_ratio=ratio,
            total_bytes=total,
            quota_bytes=quota,
            warnings=warnings,
        )
        try:
            from ops.operator_notifications import enqueue_operator_notification

            enqueue_operator_notification(
                runtime_dir,
                kind="storage_pressure",
                severity="high" if emergency else "medium",
                message=f"Storage at {ratio*100:.1f}% of quota ({total} bytes)",
            )
        except Exception:
            pass
    return state


def storage_payload(runtime_dir: str) -> dict[str, Any]:
    return load_json(storage_state_path(runtime_dir), {"pressure": False, "breakdown": {}})
