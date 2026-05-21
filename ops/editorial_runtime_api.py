"""GET /runtime/editorial/* governance endpoints."""

from __future__ import annotations

import json
from typing import Any

from editorial.governance.diversity_controls import diversity_metrics
from editorial.governance.ledger import query_decisions
from editorial.governance.operator_controls import get_operator_controls
from editorial.governance.policies_engine import policies_payload
from editorial.governance.ranking import get_last_ranking_snapshot, load_ranking_weights
from editorial.governance.reputation import reputation_snapshot
from editorial.governance.drift import compute_drift_signals


def _json(obj: Any) -> tuple[int, str, bytes]:
    return 200, "application/json", json.dumps(obj, separators=(",", ":"), default=str).encode("utf-8")


def editorial_ranking_payload(runtime_dir: str | None) -> dict[str, Any]:
    snap = get_last_ranking_snapshot(runtime_dir)
    return {
        "weights": load_ranking_weights(runtime_dir),
        "snapshot": snap,
        "deterministic": True,
    }


def editorial_policies_payload(runtime_dir: str | None) -> dict[str, Any]:
    return policies_payload(runtime_dir)


def editorial_ledger_payload(runtime_dir: str | None, *, limit: int = 50) -> dict[str, Any]:
    return {"entries": query_decisions(runtime_dir, limit=limit), "limit": limit}


def editorial_governance_status(runtime_dir: str | None) -> dict[str, Any]:
    return {
        "reputation": reputation_snapshot(runtime_dir),
        "diversity": diversity_metrics(runtime_dir),
        "operator_controls": get_operator_controls(runtime_dir),
        "drift": compute_drift_signals(runtime_dir),
    }


async def dispatch_editorial_runtime_http(
    settings: Any,
    path_only: str,
) -> tuple[int, str, bytes] | None:
    p = path_only.rstrip("/")
    rd = str(getattr(settings, "runtime_state_dir", "var/runtime"))
    if p == "/runtime/editorial/ranking":
        return _json(editorial_ranking_payload(rd))
    if p == "/runtime/editorial/policies":
        return _json(editorial_policies_payload(rd))
    if p == "/runtime/editorial/ledger":
        return _json(editorial_ledger_payload(rd))
    if p == "/runtime/editorial/status":
        return _json(editorial_governance_status(rd))
    return None
