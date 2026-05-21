"""Editorial ROI / efficiency metrics."""

from __future__ import annotations

import time
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.economics.paths import roi_daily_path
from utils.metrics import export_snapshot


def update_roi_daily(runtime_dir: str) -> dict[str, Any]:
    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    from ops.analytics.publication import publication_analytics_payload

    pub = publication_analytics_payload(runtime_dir, days=1)
    publishes = int(ctr.get("publishes") or 0)
    drafts = int(ctr.get("drafts_generated") or 0)
    suppress = int(ctr.get("skipped_intelligence_suppress") or 0)
    dup_skip = int(ctr.get("skipped_duplicates") or 0)
    ai_tok = int(ctr.get("ai_input_tokens") or 0) + int(ctr.get("ai_output_tokens") or 0)
    ai_cost = int(ctr.get("ai_cost_micro_usd") or 0) / 1_000_000.0
    interventions = int(ctr.get("drafts_rejected") or 0) + int(ctr.get("drafts_approved") or 0)
    row = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "publish_usefulness_proxy": round(publishes / max(1, drafts), 4),
        "operator_intervention_rate": round(interventions / max(1, drafts + publishes), 4),
        "duplicate_suppression_savings": dup_skip,
        "ai_tokens_per_publish": round(ai_tok / max(1, publishes), 2),
        "ai_cost_usd_per_publish": round(ai_cost / max(1, publishes), 6),
        "intelligence_suppress_rate": round(suppress / max(1, suppress + drafts), 4),
        "topic_saturation": pub.get("current", {}).get("diversity", {}).get("topic_distribution"),
        "source_value_density": pub.get("current", {}).get("diversity", {}).get("source_distribution"),
    }
    path = roi_daily_path(runtime_dir)
    data = load_json(path, {"version": 1, "days": {}})
    days = dict(data.get("days") or {})
    days[time.strftime("%Y-%m-%d", time.gmtime())] = row
    keys = sorted(days.keys(), reverse=True)[:90]
    data["days"] = {k: days[k] for k in keys}
    save_json(path, data)
    return row


def roi_payload(runtime_dir: str) -> dict[str, Any]:
    data = load_json(roi_daily_path(runtime_dir), {"days": {}})
    days = dict(data.get("days") or {})
    latest = days.get(max(days.keys(), default=""), {}) if days else {}
    return {"latest": latest, "days": days}
