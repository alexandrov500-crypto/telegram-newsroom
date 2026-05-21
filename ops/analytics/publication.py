"""Publication analytics with daily rollups."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from editorial.governance.diversity_controls import diversity_metrics
from editorial.intelligence_store import load_json, save_json


def _rollup_path(runtime_dir: str) -> Path:
    p = Path(runtime_dir).expanduser().resolve() / "analytics"
    p.mkdir(parents=True, exist_ok=True)
    return p / "publication_daily.json"


def _day_key(ts: float | None = None) -> str:
    t = time.gmtime(ts or time.time())
    return time.strftime("%Y-%m-%d", t)


def record_daily_rollup(runtime_dir: str, *, counters_delta: dict[str, int] | None = None) -> dict[str, Any]:
    path = _rollup_path(runtime_dir)
    data = load_json(path, {"version": 1, "days": {}})
    days = dict(data.get("days") or {})
    key = _day_key()
    row = dict(days.get(key) or {})
    for k, v in (counters_delta or {}).items():
        row[k] = int(row.get(k) or 0) + int(v)
    row["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    days[key] = row
    data["days"] = days
    save_json(path, data)
    return row


def update_rollup_from_runtime(runtime_dir: str) -> None:
    """Snapshot current diversity + journal stats into today's rollup."""
    from ops.resilience.publish_journal import journal_tail
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    div = diversity_metrics(runtime_dir)
    journal = journal_tail(runtime_dir, limit=500)
    finalized = sum(1 for j in journal if j.get("state") == "finalized")
    failed = sum(1 for j in journal if j.get("state") == "failed")
    path = _rollup_path(runtime_dir)
    data = load_json(path, {"version": 1, "days": {}})
    days = dict(data.get("days") or {})
    key = _day_key()
    row = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "publishes_total": int(ctr.get("publishes") or 0),
        "drafts_rejected": int(ctr.get("drafts_rejected") or 0),
        "cadence_blocked": int(ctr.get("cadence_blocked_publish") or 0),
        "skipped_suppress": int(ctr.get("skipped_intelligence_suppress") or 0),
        "journal_finalized": finalized,
        "journal_failed": failed,
        "topic_distribution": div.get("topic_distribution"),
        "source_distribution": div.get("source_distribution"),
        "suppression_counts": div.get("suppression_counts"),
    }
    days[key] = row
    data["days"] = days
    save_json(path, data)


def publication_analytics_payload(runtime_dir: str, *, days: int = 14) -> dict[str, Any]:
    from app.dependency_state import get_dependency_state
    from app.openai_circuit import get_openai_circuit
    from utils.metrics import export_snapshot

    update_rollup_from_runtime(runtime_dir)
    path = _rollup_path(runtime_dir)
    data = load_json(path, {"version": 1, "days": {}})
    day_map = dict(data.get("days") or {})
    keys = sorted(day_map.keys(), reverse=True)[: max(1, min(days, 90))]
    deps = get_dependency_state()
    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})

    intervention_rate = 0.0
    drafts = int(ctr.get("drafts_generated") or 0)
    suppress = int(ctr.get("skipped_intelligence_suppress") or 0)
    if drafts + suppress > 0:
        intervention_rate = round(suppress / (drafts + suppress), 4)

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "daily_rollups": {k: day_map[k] for k in keys},
        "current": {
            "publish_cadence": {
                "cadence_blocked_total": int(ctr.get("cadence_blocked_publish") or 0),
                "publishes_total": int(ctr.get("publishes") or 0),
            },
            "diversity": diversity_metrics(runtime_dir),
            "approval_rejection": {
                "drafts_generated": drafts,
                "drafts_rejected": int(ctr.get("drafts_rejected") or 0),
                "drafts_published": int(ctr.get("drafts_published") or 0),
            },
            "suppression_effectiveness": {
                "intelligence_suppress": suppress,
                "duplicate_signals": int(ctr.get("skipped_duplicate") or 0),
            },
            "editorial_intervention_rate": intervention_rate,
            "runtime_degradation": {
                "aggregate_status": deps.aggregate_status().value,
                "openai_circuit_open": bool(get_openai_circuit().snapshot().get("open")),
                "ai_pipeline_enabled": deps.ai_pipeline_enabled,
            },
        },
    }
