from __future__ import annotations

import json
from typing import Any

from bot.editorial.flow_health.state import load_state

MAX_METRICS_JSON_BYTES = 256_000
MAX_DAY_MAP_ENTRIES = 40
MAX_LEDGER_SUBSYSTEMS = 32
MAX_INCIDENTS = 40

_CONTINUITY_KEYS = (
    "observability_continuity",
    "convergence_continuity",
    "closure_continuity",
    "minimalism_continuity",
    "legacy_memory",
    "strategic_resilience_memory",
    "doctrine_continuity",
)

_BOUNDED_TOP_KEYS = (
    "evidence_daily",
    "evolution_ledger",
    "operational_memory",
    "doctrine_continuity",
    "strategic_resilience_memory",
    "minimalism_continuity",
    "closure_continuity",
    "legacy_memory",
    "observability_continuity",
    "convergence_continuity",
)


def _day_map_size(block: dict[str, Any]) -> int:
    for key in ("canonical_days", "converged_days", "steady_days", "quiet_days", "bounded_days"):
        days = block.get(key)
        if isinstance(days, dict):
            return len(days)
    for key in ("maturity_fingerprints",):
        fp = block.get(key)
        if isinstance(fp, dict):
            return len(fp)
    return 0


def verify_persistence_aging(
    *,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded growth of metrics_json — snapshot verification only."""
    st = metrics if metrics is not None else load_state()
    issues: list[str] = []

    raw = json.dumps({k: v for k, v in st.items() if k != "recovery_activated_at"})
    byte_size = len(raw.encode("utf-8"))
    if byte_size > MAX_METRICS_JSON_BYTES:
        issues.append("metrics_json_oversize")

    top_keys = {k for k in st if k not in ("recovery_activated_at",)}
    if len(top_keys) > 48:
        issues.append("top_level_key_explosion")

    continuity_pressure = 0.0
    continuity_checks = 0
    for key in _CONTINUITY_KEYS:
        block = st.get(key)
        if not isinstance(block, dict):
            continue
        continuity_checks += 1
        size = _day_map_size(block)
        if size > MAX_DAY_MAP_ENTRIES:
            issues.append(f"continuity_unbounded_{key}")
        continuity_pressure = max(continuity_pressure, size / MAX_DAY_MAP_ENTRIES)

    ledger = st.get("evolution_ledger") or {}
    if isinstance(ledger, dict) and len(ledger) > MAX_LEDGER_SUBSYSTEMS:
        issues.append("evolution_ledger_oversize")

    omem = st.get("operational_memory") or {}
    incidents = omem.get("incidents") if isinstance(omem, dict) else []
    if isinstance(incidents, list) and len(incidents) > MAX_INCIDENTS:
        issues.append("operational_memory_incidents_oversize")

    evidence = st.get("evidence_daily") or {}
    if isinstance(evidence, dict) and len(evidence) > MAX_DAY_MAP_ENTRIES:
        issues.append("evidence_daily_oversize")

    legacy_mem = st.get("legacy_memory")
    omem = st.get("operational_memory")
    if isinstance(legacy_mem, dict) and isinstance(omem, dict):
        if legacy_mem.keys() & omem.keys() and len(legacy_mem) > 20 and len(omem) > 20:
            issues.append("overlapping_memory_retention_keys")

    growth_rate = round(min(1.0, byte_size / MAX_METRICS_JSON_BYTES), 3)
    retention_ok = "operational_memory_incidents_oversize" not in issues

    return {
        "persistence_growth_rate": growth_rate,
        "continuity_storage_pressure": round(continuity_pressure, 3),
        "memory_retention_health": "HEALTHY" if retention_ok else "PRESSURED",
        "bounded_persistence_ok": len(issues) == 0,
        "persistence_issues": issues[:12],
        "metrics_json_bytes": byte_size,
        "bounded_keys_present": sum(1 for k in _BOUNDED_TOP_KEYS if k in st),
    }
