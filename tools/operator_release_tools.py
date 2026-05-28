#!/usr/bin/env python3
"""Operator-readable release tooling (qa-status, incident-report, etc.)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.database_url import sqlite_path_from_url


def _runtime_dir() -> Path:
    return Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))


def _db_path() -> Path | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    p = sqlite_path_from_url(raw)
    return Path(p) if p else None


def cmd_qa_status() -> int:
    from app.observability.prepublic_qa import build_prepublic_validation_report, prepublic_qa_enabled

    rd = _runtime_dir()
    report = build_prepublic_validation_report(
        db_path=_db_path(),
        runtime_dir=rd,
        log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
    )
    print(f"PREPUBLIC_QA_MODE={prepublic_qa_enabled()}")
    print(f"continuity_score={report.get('continuity', {}).get('autonomous_continuity_score')}")
    print(f"execution_graph_ready={report.get('execution_graph', {}).get('execution_graph_ready')}")
    print(f"stability_score={report.get('stability', {}).get('system_stability_score')}")
    return 0


def cmd_incident_report() -> int:
    import sqlite3

    rd = _runtime_dir()
    db = _db_path()
    lines = ["=== INCIDENT REPORT ==="]
    if db and db.is_file():
        conn = sqlite3.connect(str(db), timeout=5.0)
        from app.observability.publish_continuity import compute_autonomous_continuity_score

        lines.append(json.dumps(compute_autonomous_continuity_score(conn, runtime_dir=str(rd)), indent=2))
        conn.close()
    eg = rd / "execution_graph_report.json"
    if eg.is_file():
        lines.append("execution_graph:")
        lines.append(eg.read_text(encoding="utf-8")[:4000])
    prot = rd / "runtime_protection_state.json"
    if prot.is_file():
        lines.append("protection:")
        lines.append(prot.read_text(encoding="utf-8")[:2000])
    print("\n".join(lines))
    return 0


def cmd_release_readiness() -> int:
    from app.observability.public_readiness import evaluate_final_public_readiness

    out = evaluate_final_public_readiness(
        db_path=_db_path(),
        runtime_dir=_runtime_dir(),
        log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    v = out.get("FINAL_PUBLIC_READINESS", "NOT_READY")
    return 0 if v == "READY" else (2 if v == "CONDITIONAL" else 1)


def cmd_operator_health() -> int:
    from app.observability.runtime_health import collect_health_snapshot
    from app.observability.runtime_protection import protection_payload

    snap = collect_health_snapshot()
    prot = protection_payload(str(_runtime_dir()))
    print(json.dumps({"health": snap, "protection": prot}, indent=2, ensure_ascii=False))
    return 0


def cmd_autopublish_status() -> int:
    from app.observability.publish_continuity import is_operator_autopublish_paused
    from app.ops.autonomous_publish import auto_publish_enabled, settings_force_manual

    rd = str(_runtime_dir())
    print(f"auto_publish_enabled={auto_publish_enabled()}")
    print(f"settings_force_manual={settings_force_manual()}")
    print(f"operator_paused={is_operator_autopublish_paused(rd)}")
    try:
        from app.observability.runtime_protection import autonomous_publish_blocked

        print(f"runtime_protection_blocks={autonomous_publish_blocked(rd)}")
    except Exception:
        pass
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("qa-status")
    sub.add_parser("incident-report")
    sub.add_parser("release-readiness")
    sub.add_parser("operator-health")
    sub.add_parser("autopublish-status")
    args = p.parse_args()
    cmds = {
        "qa-status": cmd_qa_status,
        "incident-report": cmd_incident_report,
        "release-readiness": cmd_release_readiness,
        "operator-health": cmd_operator_health,
        "autopublish-status": cmd_autopublish_status,
    }
    return cmds[args.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
