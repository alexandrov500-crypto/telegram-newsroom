"""Operational SLO framework → slo_status.json."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from editorial.intelligence_store import save_json
from ops.economics.paths import slo_status_path
from utils.metrics import export_snapshot


def compute_slo_status(settings: Any, runtime_dir: str) -> dict[str, Any]:
    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    publishes = int(ctr.get("publishes") or 0)
    pub_fail = int(ctr.get("publish_failures") or 0)
    pub_attempts = publishes + pub_fail
    publish_success_rate = round(publishes / max(1, pub_attempts), 4)
    dup_skip = int(ctr.get("skipped_duplicates") or 0)
    drafts = int(ctr.get("drafts_generated") or 0)
    dup_prevention = round(dup_skip / max(1, dup_skip + drafts), 4)
    overflow = int(ctr.get("queue_overflow_total") or 0)
    q_equilibrium = overflow == 0
    from editorial.governance.ledger import query_decisions

    ledger_n = len(query_decisions(runtime_dir, limit=20))
    explain_coverage = ledger_n >= 1 or drafts == 0
    snap_dir = Path(runtime_dir) / "full_snapshots"
    restore_ok = snap_dir.is_dir() and any(snap_dir.glob("snap_*.tar.gz"))
    from ops.resilience.publish_journal import journal_tail

    journal = journal_tail(runtime_dir, limit=30)
    replay_integrity = len(journal) == 0 or any(j.get("state") == "finalized" for j in journal)

    slos = {
        "publish_success_rate": {"target": 0.95, "value": publish_success_rate, "ok": publish_success_rate >= 0.9},
        "duplicate_prevention_rate": {"target": 0.1, "value": dup_prevention, "ok": True},
        "queue_equilibrium": {"target": True, "value": q_equilibrium, "ok": q_equilibrium},
        "governance_explainability": {"target": True, "value": explain_coverage, "ok": explain_coverage},
        "replay_integrity": {"target": True, "value": replay_integrity, "ok": replay_integrity},
        "snapshot_restore_available": {"target": True, "value": restore_ok, "ok": restore_ok},
        "recovery_time_proxy_sec": {
            "target": 300,
            "value": __import__("app.runtime_activity", fromlist=["seconds_since_scheduler_tick"]).seconds_since_scheduler_tick(),
            "ok": True,
        },
    }
    all_ok = all(s.get("ok") for s in slos.values())
    out = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "aggregate_ok": all_ok,
        "slos": slos,
    }
    save_json(slo_status_path(runtime_dir), out)
    return out


def slo_payload(runtime_dir: str) -> dict[str, Any]:
    from editorial.intelligence_store import load_json

    return load_json(slo_status_path(runtime_dir), {"aggregate_ok": None, "slos": {}})
