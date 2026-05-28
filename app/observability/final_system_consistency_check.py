"""Final system consistency check (launch blocker if INCONSISTENT)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.execution_graph_report import build_execution_graph_report
from app.observability.release_contract_evaluator import collect_contract_checks
from app.observability.validation_contract import evaluate_required_only_contract
from utils.database_url import sqlite_path_from_url


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_system_consistency_report(runtime_dir: str) -> dict[str, Any]:
    rd = Path(runtime_dir).expanduser().resolve()
    blockers: list[str] = []

    contract = collect_contract_checks(str(rd))
    required_eval = evaluate_required_only_contract(required=list(contract.get("required_checks") or []))
    if str(required_eval.get("verdict")) != "READY_FOR_PUBLIC":
        blockers.extend(list(required_eval.get("blockers") or []))

    e2e = _read_json(rd / "final_e2e_production_test_report.json")
    if e2e and not bool(e2e.get("ok")):
        blockers.append("e2e_production_test_failed")

    sim = _read_json(rd / "telegram_safe_simulation_report.json")
    if sim and not bool(sim.get("ok")):
        blockers.append("telegram_safe_simulation_failed")

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    dbp = sqlite_path_from_url(raw)
    if dbp and Path(dbp).is_file():
        conn = sqlite3.connect(str(dbp), timeout=5.0)
        dup = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT telegram_post_id, COUNT(*) c
              FROM published_posts
              GROUP BY telegram_post_id
              HAVING c > 1
            )
            """
        ).fetchone()
        no_final = conn.execute(
            """
            SELECT COUNT(*) FROM published_posts pp
            JOIN drafts d ON d.id = pp.draft_id
            WHERE COALESCE(d.status, '') NOT IN ('published', 'approved', 'committed_draft')
            """
        ).fetchone()
        conn.close()
        if int((dup or [0])[0] or 0) > 0:
            blockers.append("duplicate_publish_detected")
        if int((no_final or [0])[0] or 0) > 0:
            blockers.append("publish_finalize_order_invalid")
    else:
        blockers.append("database_unavailable_for_consistency")

    eg = build_execution_graph_report(
        db_path=Path(dbp) if dbp and Path(dbp).is_file() else None,
        runtime_dir=rd,
        log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
        window_ticks=200,
    )
    if str(eg.get("verdict") or "") != "PASS":
        blockers.append("execution_graph_inconsistent")
    if int(eg.get("critical_tick_count") or 0) > 0:
        blockers.append("execution_graph_critical_ticks")

    verdict = "CONSISTENT" if not blockers else "INCONSISTENT"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "SYSTEM_CONSISTENCY_VERDICT": verdict,
        "blockers": sorted(set(blockers)),
        "execution_graph": {
            "verdict": eg.get("verdict"),
            "consistency_rate": eg.get("consistency_rate"),
            "critical_tick_count": eg.get("critical_tick_count"),
        },
        "required_contract_eval": required_eval,
    }


def write_system_consistency_report(runtime_dir: str, report: dict[str, Any]) -> Path:
    out = Path(runtime_dir).expanduser().resolve() / "system_consistency_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
