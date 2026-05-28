"""Final public readiness verdict (NOT_READY / CONDITIONAL / READY)."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.observability.publish_continuity import compute_autonomous_continuity_score, is_operator_autopublish_paused
from app.observability.prepublic_qa import prepublic_qa_enabled


def evaluate_final_public_readiness(
    *,
    db_path: Path | None,
    runtime_dir: Path,
    log_path: Path,
) -> dict[str, Any]:
    fails: list[str] = []
    warns: list[str] = []

    if not db_path or not db_path.is_file():
        return {
            "FINAL_PUBLIC_READINESS": "NOT_READY",
            "blockers": ["database_missing"],
            "warnings": [],
        }

    conn = sqlite3.connect(str(db_path), timeout=5.0)

    from app.observability.execution_graph_report import build_execution_graph_report
    from app.observability.runtime_resilience_report import evaluate_public_go_resilience
    from app.observability.burnin_eval import publishability_metrics

    eg = build_execution_graph_report(
        db_path=db_path,
        runtime_dir=runtime_dir,
        log_path=log_path,
        window_ticks=100,
    )
    if not eg.get("execution_graph_ready"):
        fails.append("execution_graph_not_ready")
    if float(eg.get("consistency_rate") or 0) < 1.0:
        fails.append(f"execution_consistency:{eg.get('consistency_rate')}")
    if int(eg.get("critical_tick_count") or 0) > 0:
        fails.append("execution_graph_critical_ticks")

    res_fails, res_warns = evaluate_public_go_resilience(runtime_dir)
    fails.extend(res_fails)
    warns.extend(res_warns)

    continuity = compute_autonomous_continuity_score(conn, runtime_dir=str(runtime_dir))
    min_cont = float(os.getenv("PUBLIC_GO_MIN_CONTINUITY_SCORE", "55"))
    if float(continuity.get("autonomous_continuity_score") or 0) < min_cont:
        fails.append(f"autonomous_continuity_low:{continuity.get('autonomous_continuity_score')}")

    gap = continuity.get("publish_gap_hours")
    if gap is not None and float(gap) > float(os.getenv("PUBLIC_GO_MAX_PUBLISH_GAP_HOURS", "12")):
        fails.append(f"publish_gap_violation:{gap}h")

    pub = publishability_metrics(conn)
    pub_24 = int(pub.get("publishes_24h") or 0)
    draft_24 = int(pub.get("committed_draft_24h") or 0)
    if pub_24 < 1 and not prepublic_qa_enabled():
        fails.append("no_publish_24h")

    min_pub_rate = float(os.getenv("PUBLIC_GO_MIN_PUBLISH_SUCCESS_RATE", "0.0"))
    psr = continuity.get("publish_success_rate_24h")
    if psr is not None and float(psr) < min_pub_rate and draft_24 > 0:
        fails.append(f"publish_success_rate_low:{psr}")

    if int(pub.get("running_ticks") or 0) > 0:
        fails.append(f"scheduler_freeze_or_stuck_ticks:{pub['running_ticks']}")

    alerts_path = runtime_dir / "ops" / "pending_notifications.jsonl"
    if alerts_path.is_file():
        recent = alerts_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-20:]
        crit = sum(1 for ln in recent if "critical" in ln.lower())
        if crit >= int(os.getenv("PUBLIC_GO_RECENT_CRITICAL_ALERTS", "3")):
            fails.append(f"operator_alerts_critical_recent:{crit}")

    protection_path = runtime_dir / "runtime_protection_state.json"
    if protection_path.is_file():
        try:
            pst = json.loads(protection_path.read_text(encoding="utf-8"))
            if pst.get("last_critical_at"):
                hist = pst.get("transition_history") or []
                if any(h.get("to") == "critical" for h in hist[-50:]):
                    fails.append("unresolved_critical_runtime_history")
        except (OSError, json.JSONDecodeError):
            pass

    conn.close()

    if any("warn:" in w or "elevated" in w for w in warns) and not fails:
        verdict = "CONDITIONAL"
    elif fails:
        verdict = "NOT_READY"
    else:
        verdict = "READY"

    return {
        "FINAL_PUBLIC_READINESS": verdict,
        "blockers": fails,
        "warnings": warns,
        "continuity": continuity,
        "execution_graph_ready": eg.get("execution_graph_ready"),
        "drafts_24h": draft_24,
        "publishes_24h": pub_24,
        "operator_autopublish_paused": is_operator_autopublish_paused(str(runtime_dir)),
    }
