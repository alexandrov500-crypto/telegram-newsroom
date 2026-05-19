from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_BASELINE_RECORDS = 90


def capture_operational_baseline(
    report: dict[str, Any],
    *,
    week_id: str | None = None,
) -> dict[str, Any]:
    """Weekly stability snapshot — not analytics, not a dashboard."""
    now = datetime.now(timezone.utc)
    week_id = week_id or now.strftime("%G-W%V")
    p = report.get("persistence") or {}
    d = report.get("digest") or {}
    s = report.get("scheduler") or {}
    t = report.get("telemetry") or {}
    r = report.get("restart") or {}
    deg = report.get("degradation") or {}
    aging = report.get("operational_aging") or {}
    quiet = d.get("quiet_modes") or {}

    return {
        "recorded_at": now.isoformat(),
        "week_id": week_id,
        "infrastructure_validation_ok": report.get("infrastructure_validation_ok"),
        "checks_passed": report.get("checks_passed"),
        "checks_total": report.get("checks_total"),
        "summary_lines": list(report.get("summary_lines") or []),
        "runtime": {
            "restart_count": r.get("recovery_activation_count"),
            "recovery_active": r.get("recovery_active"),
            "runtime_restart_health": r.get("runtime_restart_health"),
            "scheduler_stability": s.get("scheduler_stability"),
            "stalled_loops": s.get("stalled_loops"),
            "publish_continuity_ok": s.get("publish_continuity_ok"),
            "degradation_mode": deg.get("degradation_mode"),
            "degraded_runtime_recovery": deg.get("degraded_runtime_recovery"),
        },
        "persistence": {
            "metrics_json_bytes": p.get("metrics_json_bytes"),
            "persistence_growth_rate": p.get("persistence_growth_rate"),
            "continuity_storage_pressure": p.get("continuity_storage_pressure"),
            "memory_retention_health": p.get("memory_retention_health"),
            "bounded_persistence_ok": p.get("bounded_persistence_ok"),
        },
        "digest": {
            "digest_line_count": d.get("digest_line_count"),
            "digest_noise_drift": d.get("digest_noise_drift"),
            "invisible_digest_stability": d.get("invisible_digest_stability"),
            "stewardship_verbosity_pressure": d.get("stewardship_verbosity_pressure"),
            "invisible_digest": quiet.get("invisible_digest"),
            "ultra_quiet": quiet.get("ultra_quiet"),
            "finalization_quiet": quiet.get("finalization_quiet"),
        },
        "telemetry": {
            "telemetry_growth_rate": t.get("telemetry_growth_rate"),
            "collector_integrity_ok": t.get("collector_integrity_ok"),
            "telemetry_fragmentation_detected": t.get("telemetry_fragmentation_detected"),
            "canonical_telemetry_stability": t.get("canonical_telemetry_stability"),
        },
        "calmness": {
            "hidden_entropy_observed": deg.get("hidden_entropy_observed"),
            "operational_aging_ok": deg.get("operational_aging_ok"),
            "long_horizon_calm": aging.get("long_horizon_calm"),
            "operational_fatigue_detected": aging.get("operational_fatigue_detected"),
            "slow_drift_risk": aging.get("slow_drift_risk"),
        },
    }


def append_baseline_record(
    baseline: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> Path:
    """Append one JSON line — bounded retention, fail-open."""
    root = output_dir or Path("var/ops/stability")
    root.mkdir(parents=True, exist_ok=True)
    path = root / "weekly_baseline.jsonl"
    try:
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps(baseline, default=str))
        lines = lines[-MAX_BASELINE_RECORDS:]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except Exception:
        pass
    return path


def load_baseline_history(
    *,
    output_dir: Path | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Recent weekly records for manual drift review."""
    path = (output_dir or Path("var/ops/stability")) / "weekly_baseline.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if line.strip():
                out.append(json.loads(line))
    except Exception:
        return []
    return out
