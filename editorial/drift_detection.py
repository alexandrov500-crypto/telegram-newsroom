"""Rolling editorial quality drift heuristics (snapshots in JSON)."""

from __future__ import annotations

import time
from typing import Any

from editorial.intelligence_store import drift_snapshots_path, load_json, save_json


def append_drift_snapshot(runtime_dir: str | None, snapshot: dict[str, Any], *, max_entries: int = 48) -> None:
    path = drift_snapshots_path(runtime_dir)
    data = load_json(path, {"version": 1, "snapshots": []})
    snaps = list(data.get("snapshots") or [])
    row = {"ts": time.time(), "data": dict(snapshot)}
    snaps.insert(0, row)
    data["snapshots"] = snaps[:max_entries]
    save_json(path, data)


def compact_drift_snapshots(
    runtime_dir: str | None,
    *,
    max_entries: int = 48,
    max_age_sec: float | None = None,
) -> dict[str, Any]:
    """Age + count trim for drift snapshot file (best-effort)."""
    path = drift_snapshots_path(runtime_dir)
    data = load_json(path, {"version": 1, "snapshots": []})
    snaps = [x for x in (data.get("snapshots") or []) if isinstance(x, dict)]
    now = time.time()
    if max_age_sec is not None:
        ma = float(max_age_sec)
        snaps = [s for s in snaps if now - float(s.get("ts") or 0.0) <= ma]
    before = len(snaps)
    snaps = snaps[: max(1, min(int(max_entries), 500))]
    data["snapshots"] = snaps
    save_json(path, data)
    return {"path": str(path), "before": before, "kept": len(snaps)}


def evaluate_editorial_drift(
    runtime_dir: str | None,
    *,
    current_metrics: dict[str, Any],
    current_feedback: dict[str, Any] | None,
    append_snapshot: bool = True,
) -> dict[str, Any]:
    """
    Compare latest snapshot to previous for simple deltas (warnings only).
    ``current_metrics`` should include acceptance_proxy, suppression_rate, avg_confidence if available.
    """
    path = drift_snapshots_path(runtime_dir)
    data = load_json(path, {"version": 1, "snapshots": []})
    snaps = [x for x in (data.get("snapshots") or []) if isinstance(x, dict)]
    prev = snaps[0].get("data") if snaps else None
    warns: list[str] = []
    acc = float((current_feedback or {}).get("acceptance_proxy") or 0.0)
    if prev and isinstance(prev, dict):
        p_acc = float(prev.get("acceptance_proxy") or 0.0)
        if p_acc > 0.55 and acc < p_acc - 0.12:
            warns.append("drift_falling_acceptance")
        p_sup = float(prev.get("suppression_rate") or 0.0)
        c_sup = float(current_metrics.get("suppression_rate") or 0.0)
        if c_sup > p_sup + 0.15:
            warns.append("drift_rising_suppression_rate")
        p_conf = float(prev.get("avg_confidence") or 0.0)
        c_conf = float(current_metrics.get("avg_confidence") or 0.0)
        if p_conf > 0.45 and c_conf < p_conf - 0.12:
            warns.append("drift_falling_confidence")
    snap = {
        "acceptance_proxy": acc,
        "suppression_rate": float(current_metrics.get("suppression_rate") or 0.0),
        "avg_confidence": float(current_metrics.get("avg_confidence") or 0.0),
        "avg_headline_quality": float(current_metrics.get("avg_headline_quality") or 0.0),
        "manual_edit_rate": float(current_metrics.get("manual_edit_rate") or 0.0),
    }
    if append_snapshot:
        append_drift_snapshot(runtime_dir, snap)
    return {
        "schema_version": 1,
        "warnings": warns,
        "snapshot": snap,
        "had_baseline": prev is not None,
        "append_snapshot": append_snapshot,
    }
