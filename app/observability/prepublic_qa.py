"""PREPUBLIC_QA_MODE — stricter observability and validation report (no product features)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


def prepublic_qa_enabled() -> bool:
    if os.getenv("PREPUBLIC_QA_MODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    try:
        from app.ops.controlled_rollout import rollout_qa_mirror_enabled

        return rollout_qa_mirror_enabled()
    except Exception:
        return False


def record_publish_decision_explanation(
    runtime_dir: str,
    *,
    draft_id: int,
    decision: str,
    detail: dict[str, Any] | None = None,
) -> None:
    if not prepublic_qa_enabled():
        return
    path = Path(runtime_dir) / "prepublic_publish_decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "draft_id": draft_id,
        "decision": decision,
        "detail": detail or {},
    }
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        log_event(logger, "prepublic_qa.persist_failed", error=repr(exc)[:120])


async def mirror_publish_to_qa_chat(
    bot: Any,
    settings: Any,
    *,
    draft_id: int,
    content_preview: str,
    channel_message_id: int | None,
) -> None:
    if not prepublic_qa_enabled():
        return
    chat_id = getattr(settings, "moderation_chat_id", None)
    if not chat_id:
        return
    text = (
        f"[QA mirror] draft #{draft_id}\n"
        f"channel_msg={channel_message_id}\n"
        f"{content_preview[:500]}"
    )
    try:
        await bot.send_message(int(chat_id), text[:4000], disable_web_page_preview=True)
    except Exception as exc:
        log_event(logger, "prepublic_qa.mirror_failed", draft_id=draft_id, error=repr(exc)[:200])


def build_prepublic_validation_report(
    *,
    db_path: Path | None,
    runtime_dir: Path,
    log_path: Path,
) -> dict[str, Any]:
    from app.observability.burnin_eval import publishability_metrics, scan_log_contract
    from app.observability.execution_graph_report import build_execution_graph_report
    from app.observability.publish_continuity import compute_autonomous_continuity_score
    from app.observability.runtime_resilience_report import build_runtime_resilience_section
    from app.observability.stability_metrics import compute_system_stability_score

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prepublic_qa_mode": True,
    }
    if db_path and db_path.is_file():
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        report["publishability"] = publishability_metrics(conn)
        report["continuity"] = compute_autonomous_continuity_score(conn, runtime_dir=str(runtime_dir))
        report["stability"] = compute_system_stability_score(conn)
        conn.close()
    else:
        report["publishability"] = {}
        report["continuity"] = {}
        report["stability"] = {}

    report["execution_graph"] = build_execution_graph_report(
        db_path=db_path,
        runtime_dir=runtime_dir,
        log_path=log_path,
        window_ticks=100,
    )
    report["runtime_resilience"] = build_runtime_resilience_section(runtime_dir)
    report["log_contract"] = scan_log_contract(log_path)
    report["anomaly_counts"] = {
        "execution_graph_critical": report["execution_graph"].get("critical_tick_count", 0),
        "log_openai_failed": report["log_contract"].get("openai_summarize_failed", 0),
        "log_rule_fallback": report["log_contract"].get("rule_fallback", 0),
    }
    return report


def write_prepublic_validation_report(
    *,
    db_path: Path | None,
    runtime_dir: Path,
    log_path: Path,
) -> Path:
    report = build_prepublic_validation_report(
        db_path=db_path,
        runtime_dir=runtime_dir,
        log_path=log_path,
    )
    dest = runtime_dir / "prepublic_validation_report.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest
