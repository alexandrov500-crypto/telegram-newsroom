"""Exportable transparency artifacts for external audit."""

from __future__ import annotations

import json
import time
from typing import Any

from ops.audit.search import search_audit


def build_transparency_bundle(settings: Any, *, hours: float = 24.0) -> dict[str, Any]:
    rd = settings.runtime_state_dir
    since = time.time() - max(3600.0, hours * 3600.0)
    from editorial.governance.ledger import query_decisions
    from editorial.governance.policies_engine import policies_payload
    from editorial.governance.ranking import get_last_ranking_snapshot
    from ops.resilience.deployment_manifest import load_deployment_manifest
    from ops.resilience.publish_journal import journal_tail

    audit = search_audit(rd, since_unix=since, limit=100)
    return {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window_hours": hours,
        "deployment_manifest": load_deployment_manifest(rd),
        "governance_decisions": query_decisions(rd, limit=80),
        "ranking_snapshot": get_last_ranking_snapshot(rd),
        "policies": policies_payload(rd),
        "publish_journal": journal_tail(rd, limit=80),
        "audit_sample": audit.get("results") or [],
        "publish_provenance_summary": _publish_provenance_summary(rd, since),
    }


def _publish_provenance_summary(runtime_dir: str, since: float) -> dict[str, Any]:
    from ops.resilience.publish_journal import journal_tail

    rows = journal_tail(runtime_dir, limit=200)
    finalized = [r for r in rows if r.get("state") == "finalized" and float(r.get("ts_unix") or 0) >= since]
    suppress_audit = search_audit(runtime_dir, entity="suppression", since_unix=since, limit=50)
    return {
        "finalized_count": len(finalized),
        "suppression_events": len(suppress_audit.get("results") or []),
        "recent_finalized": finalized[:15],
    }


def write_transparency_export(settings: Any, out_path: str, *, hours: float = 24.0) -> str:
    bundle = build_transparency_bundle(settings, hours=hours)
    p = json.dumps(bundle, indent=2, default=str)
    path = __import__("pathlib").Path(out_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p, encoding="utf-8")
    return str(path)
