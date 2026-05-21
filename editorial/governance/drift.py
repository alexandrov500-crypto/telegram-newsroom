"""Editorial drift detection (concentration, entropy, instability)."""

from __future__ import annotations

import math
import time
from typing import Any

from editorial.governance.diversity_controls import diversity_metrics
from editorial.governance.paths import governance_state_path
from editorial.intelligence_store import drift_snapshots_path, load_json, save_json
from utils.structured_log import log_event


def _entropy(dist: dict[str, float]) -> float:
    if not dist:
        return 0.0
    vals = [float(v) for v in dist.values() if float(v) > 0]
    if not vals:
        return 0.0
    return round(-sum(p * math.log(p + 1e-12) for p in vals), 4)


def compute_drift_signals(runtime_dir: str | None) -> dict[str, Any]:
    div = diversity_metrics(runtime_dir)
    td = div.get("topic_distribution") or {}
    sd = div.get("source_distribution") or {}
    topic_entropy = _entropy(td)
    source_entropy = _entropy(sd)
    top_topic = max(td.values()) if td else 0.0
    top_source = max(sd.values()) if sd else 0.0
    sup = div.get("suppression_counts") or {}
    dup_sup = int(sup.get("duplicate_risk_elevated") or 0) + int(sup.get("duplicate_burst") or 0)
    state = load_json(governance_state_path(runtime_dir), {})
    prev = load_json(drift_snapshots_path(runtime_dir), {"history": []})
    hist = list(prev.get("history") or [])
    ranking_instability = 0.0
    if len(hist) >= 2:
        a, b = hist[-2], hist[-1]
        ranking_instability = abs(float(a.get("top_topic_share") or 0) - float(b.get("top_topic_share") or 0))
    snap = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "topic_entropy": topic_entropy,
        "source_entropy": source_entropy,
        "top_topic_share": round(float(top_topic), 4),
        "top_source_share": round(float(top_source), 4),
        "duplicate_suppressions": dup_sup,
        "ranking_instability": round(ranking_instability, 4),
    }
    hist.append(snap)
    prev["history"] = hist[-48:]
    save_json(drift_snapshots_path(runtime_dir), prev)
    warnings: list[str] = []
    if top_topic >= 0.45:
        warnings.append("topic_concentration_high")
    if top_source >= 0.5:
        warnings.append("source_concentration_high")
    if topic_entropy < 1.2 and sum(td.values()) > 5:
        warnings.append("topic_entropy_low")
    if dup_sup >= 10:
        warnings.append("duplicate_suppressions_rising")
    if ranking_instability >= 0.2:
        warnings.append("ranking_instability")
    snap["warnings"] = warnings
    snap["alert"] = bool(warnings)
    return snap


def check_editorial_drift(runtime_dir: str | None, *, logger: Any = None) -> dict[str, Any]:
    snap = compute_drift_signals(runtime_dir)
    if snap.get("alert") and logger is not None:
        warnings = list(snap.get("warnings") or [])
        log_event(
            logger,
            "editorial.drift.warning",
            warnings=warnings,
            topic_entropy=snap.get("topic_entropy"),
            source_entropy=snap.get("source_entropy"),
            top_topic_share=snap.get("top_topic_share"),
            top_source_share=snap.get("top_source_share"),
        )
        try:
            from ops.operator_notifications import notify_drift_warning

            notify_drift_warning(runtime_dir or "", warnings)
        except Exception:
            pass
    return snap
