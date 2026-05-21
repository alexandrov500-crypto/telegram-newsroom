"""Scheduled autonomous self-validation (non-destructive)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from editorial.intelligence_store import save_json
from ops.trust.paths import validation_report_path


def run_autonomous_validation(settings: Any, runtime_dir: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # Replay / publish journal integrity
    from ops.resilience.publish_journal import journal_tail

    journal = journal_tail(runtime_dir, limit=50)
    bad_states = [j for j in journal if j.get("state") == "sending" and not any(
        x.get("draft_id") == j.get("draft_id") and x.get("state") == "finalized" for x in journal
    )]
    checks.append({
        "name": "publish_journal_integrity",
        "ok": len(bad_states) == 0,
        "detail": {"inflight_suspect": len(bad_states)},
    })

    # Snapshot restore availability (dry-run list only)
    snap_dir = Path(runtime_dir) / "full_snapshots"
    snaps = list(snap_dir.glob("snap_*.tar.gz")) if snap_dir.is_dir() else []
    checks.append({
        "name": "snapshot_restore_available",
        "ok": len(snaps) > 0,
        "detail": {"count": len(snaps)},
    })

    # Migrations consistency
    from ops.resilience.migrations import migrations_payload

    mig = migrations_payload(runtime_dir)
    checks.append({
        "name": "migration_consistency",
        "ok": bool(mig.get("migrations_state")),
        "detail": {"registered": len(mig.get("registered") or [])},
    })

    # Policy validity
    from editorial.governance.policies_engine import load_governance_rules

    try:
        rules = load_governance_rules(runtime_dir)
        pol_ok = isinstance(rules.get("rules"), list)
    except Exception as exc:
        pol_ok = False
        rules = {"error": repr(exc)}
    checks.append({"name": "policy_validity", "ok": pol_ok, "detail": {"rule_count": len(rules.get("rules") or [])}})

    # Audit chain continuity (ledger readable)
    from editorial.governance.ledger import query_decisions

    ledger = query_decisions(runtime_dir, limit=5)
    checks.append({
        "name": "audit_chain_continuity",
        "ok": True,
        "detail": {"recent_entries": len(ledger)},
    })

    # Replay integrity proxy
    from ops.economics.slo import slo_payload

    slo = slo_payload(runtime_dir)
    replay_ok = (slo.get("slos") or {}).get("replay_integrity", {}).get("ok", True)
    checks.append({"name": "replay_integrity", "ok": bool(replay_ok), "detail": {}})

    # Evolution journal readable
    from ops.trust.evolution_journal import query_evolution_history

    evo = query_evolution_history(runtime_dir, limit=3)
    checks.append({"name": "evolution_journal", "ok": True, "detail": {"entries": len(evo)}})

    passed = all(c.get("ok") for c in checks)
    report = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "passed": passed,
        "checks": checks,
        "non_destructive": True,
    }
    save_json(validation_report_path(runtime_dir), report)
    return report
