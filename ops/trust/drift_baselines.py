"""Long-term governance drift baselines."""

from __future__ import annotations

import math
import time
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.trust.paths import drift_baselines_path
from utils.structured_log import log_event

logger = __import__("logging").getLogger(__name__)


def _entropy(dist: dict[str, float]) -> float:
    if not dist:
        return 0.0
    vals = [float(v) for v in dist.values() if float(v) > 0]
    return round(-sum(p * math.log(p + 1e-12) for p in vals), 4) if vals else 0.0


def update_drift_baselines(runtime_dir: str) -> dict[str, Any]:
    from editorial.governance.diversity_controls import diversity_metrics
    from editorial.governance.drift import compute_drift_signals
    from ops.audit.search import collect_audit_records

    div = diversity_metrics(runtime_dir)
    drift = compute_drift_signals(runtime_dir)
    records = collect_audit_records(runtime_dir)
    suppress_n = sum(1 for r in records[-500:] if r.get("entity") == "suppression")
    total_n = max(1, len(records[-500:]))
    snap = {
        "topic_entropy": _entropy(div.get("topic_distribution") or {}),
        "source_entropy": _entropy(div.get("source_distribution") or {}),
        "top_topic_share": float(drift.get("top_topic_share") or 0),
        "top_source_share": float(drift.get("top_source_share") or 0),
        "suppression_ratio": round(suppress_n / total_n, 4),
        "drift_warning_rate": len(drift.get("warnings") or []),
    }
    data = load_json(drift_baselines_path(runtime_dir), {"version": 1, "ema": {}, "samples": 0})
    ema = dict(data.get("ema") or {})
    n = int(data.get("samples") or 0)
    alpha = 0.08 if n > 10 else 0.25
    for k, v in snap.items():
        prev = float(ema.get(k) or v)
        ema[k] = round((1 - alpha) * prev + alpha * float(v), 4)
    data["ema"] = ema
    data["samples"] = n + 1
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["last_snapshot"] = snap
    save_json(drift_baselines_path(runtime_dir), data)
    return data


def assess_drift_vs_baseline(runtime_dir: str) -> dict[str, Any]:
    data = update_drift_baselines(runtime_dir)
    ema = dict(data.get("ema") or {})
    cur = dict(data.get("last_snapshot") or {})
    warnings: list[str] = []
    deviations: list[dict[str, Any]] = []
    thresholds = {
        "topic_entropy": 0.35,
        "source_entropy": 0.35,
        "top_topic_share": 0.20,
        "top_source_share": 0.22,
        "suppression_ratio": 0.15,
    }
    for key, thr in thresholds.items():
        base = float(ema.get(key) or 0)
        now = float(cur.get(key) or 0)
        delta = abs(now - base)
        if delta > thr:
            warnings.append(f"baseline_deviation_{key}")
            deviations.append({"metric": key, "baseline": base, "current": now, "delta": round(delta, 4)})
    if warnings:
        log_event(logger, "governance.baseline.warning", warnings=warnings, deviations=deviations[:8])
    return {
        "within_baseline": len(warnings) == 0,
        "warnings": warnings,
        "deviations": deviations,
        "ema_baseline": ema,
        "current": cur,
        "samples": data.get("samples"),
    }
