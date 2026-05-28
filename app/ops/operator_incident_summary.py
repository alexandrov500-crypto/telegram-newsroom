"""Operator-facing concise incident summaries."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


def _summary_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "latest_incident_summary.json"


def _first_bad_event(runtime_dir: str) -> str:
    p = Path(runtime_dir).expanduser().resolve() / "ops" / "pending_notifications.jsonl"
    if not p.is_file():
        return ""
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]:
        if "critical" in ln.lower() or "corrupt" in ln.lower():
            return ln[:220]
    return ""


def build_incident_summary(runtime_dir: str) -> dict[str, Any]:
    from app.observability.runtime_protection import protection_payload
    from app.observability.telegram_production import production_validation_report
    from app.observability.publish_continuity import autopublish_pause_path
    from app.observability.burnin_validation import load_burnin_validation
    from app.ops.public_incident_safety import incident_payload

    prot = protection_payload(runtime_dir)
    inc = incident_payload(runtime_dir)
    tg = production_validation_report()
    burn = load_burnin_validation(runtime_dir)
    kinds: list[str] = []
    if str(prot.get("current_state")) == "critical":
        kinds.append("CRITICAL runtime event")
    if not bool((tg or {}).get("ok")):
        kinds.append("Telegram outage/degradation")
    if inc.get("frozen"):
        kinds.append("rollback/autopublish freeze")
    try:
        if float(((burn.get("metrics") or {}).get("publish_continuity") or {}).get("autonomous_continuity_score") or 100) < 45:
            kinds.append("publish continuity break")
    except Exception:
        pass
    if (burn.get("burnin_verdict") or burn.get("BURNIN_VERDICT")) == "FAIL":
        kinds.append("burn-in failure")
    try:
        from app.observability.execution_graph_report import build_execution_graph_report
        from utils.database_url import sqlite_path_from_url

        dbp = sqlite_path_from_url(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db"))
        eg = build_execution_graph_report(
            db_path=Path(dbp) if dbp else None,
            runtime_dir=Path(runtime_dir),
            log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
            window_ticks=100,
        )
        if int(eg.get("critical_tick_count") or 0) > 0:
            kinds.append("execution graph corruption")
    except Exception:
        pass
    if int(inc.get("diagnostics_count") or 0) > 0:
        kinds.append("incident diagnostics captured")
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "incident_types": kinds or ["none_detected"],
        "probable_root_cause": ",".join(list(prot.get("active_protections") or [])[:4]) or ",".join(list((tg or {}).get("blockers") or [])[:3]) or "investigate_logs",
        "first_bad_event": _first_bad_event(runtime_dir),
        "active_protections": list(prot.get("active_protections") or [])[:8],
        "affected_ticks": int(inc.get("diagnostics_count") or 0),
        "autopublish_paused": autopublish_pause_path(runtime_dir).is_file(),
        "suggested_next_actions": [
            "make incident-report",
            "make autopublish-status",
            "/runtime_state",
            "/continuity",
        ],
    }
    return summary


def persist_incident_summary(runtime_dir: str, summary: dict[str, Any]) -> Path:
    p = _summary_path(runtime_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def _as_telegram_message(summary: dict[str, Any]) -> str:
    sev = "🔴" if "CRITICAL runtime event" in (summary.get("incident_types") or []) else "🟠"
    lines = [
        f"{sev} Incident summary",
        f"Cause: {summary.get('probable_root_cause')}",
        f"Protections: {', '.join(summary.get('active_protections') or ['none'])}",
        f"Affected ticks: {summary.get('affected_ticks')}",
        f"First event: {str(summary.get('first_bad_event') or 'n/a')[:120]}",
        f"Actions: {', '.join(summary.get('suggested_next_actions') or [])}",
    ]
    return "\n".join(lines)[:900]


async def run_operator_incident_summary_heartbeat(settings: Any, *, bot: Any | None = None) -> dict[str, Any]:
    runtime_dir = settings.runtime_state_dir
    summary = build_incident_summary(runtime_dir)
    p = persist_incident_summary(runtime_dir, summary)
    log_event(logger, "operator_incident_summary.updated", path=str(p))
    # Push only when incident is material and bot available.
    if bot is not None and any(
        x in (summary.get("incident_types") or [])
        for x in ("CRITICAL runtime event", "rollback/autopublish freeze")
    ):
        try:
            from ops.operator_notifications import enqueue_operator_notification

            enqueue_operator_notification(
                runtime_dir,
                kind="incident_summary",
                severity="critical",
                message=_as_telegram_message(summary),
                fields=summary,
            )
        except Exception:
            pass
    return summary
