#!/usr/bin/env python3
"""Generate human-readable operational report (JSON + Markdown)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def build_report(settings: Any, *, hours: float) -> dict[str, Any]:
    from app.build_provenance import load_build_provenance
    from app.dependency_state import get_dependency_state
    from app.openai_circuit import get_openai_circuit
    from app.runtime_lifecycle import runtime_id, uptime_sec
    from dashboard.timeline import load_timeline_tail
    from ops.analytics.publication import publication_analytics_payload
    from ops.audit.search import search_audit
    from ops.control.journal import query_control_actions
    from ops.runtime_api import list_recent_incidents
    from ops.resilience.publish_journal import journal_tail
    from ops.runtime_timeline import timeline_snapshot

    rd = settings.runtime_state_dir
    since = time.time() - hours * 3600.0
    prov = load_build_provenance()
    deps = get_dependency_state()
    circuit = get_openai_circuit().snapshot()

    return {
        "report_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window_hours": hours,
        "runtime_id": runtime_id(),
        "uptime_sec": round(uptime_sec(), 2),
        "build": prov.to_dict(),
        "uptime_summary": {
            "aggregate_status": deps.aggregate_status().value,
            "ai_pipeline_enabled": deps.ai_pipeline_enabled,
            "collector_enabled": deps.collector_enabled,
            "polling_active": deps.polling_active,
        },
        "incidents": list_recent_incidents(settings, limit=15),
        "recoveries": search_audit(rd, entity="runtime_recovery", since_unix=since, limit=20),
        "publish_stats": publication_analytics_payload(rd, days=max(1, int(hours / 24) + 1)),
        "publish_journal_tail": journal_tail(rd, limit=30),
        "editorial_drift": search_audit(rd, entity="drift_warning", since_unix=since, limit=20),
        "anomalies": search_audit(rd, entity="anomaly", since_unix=since, limit=20),
        "operator_interventions": query_control_actions(rd, since_unix=since, limit=40),
        "queue_behavior": {},
        "openai": {
            "circuit": circuit,
            "failures_note": "see metrics counters in publication_stats",
        },
        "timeline_file": load_timeline_tail(rd, limit=40),
        "timeline_memory": [e.to_dict() for e in timeline_snapshot(limit=40)],
        "audit_suppressions": search_audit(rd, entity="suppression", since_unix=since, limit=30),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Newsroom operational report",
        "",
        f"- Generated: {report.get('generated_at')}",
        f"- Window: {report.get('window_hours')}h",
        f"- Runtime ID: `{report.get('runtime_id')}`",
        f"- Uptime: {report.get('uptime_sec')}s",
        f"- Status: {(report.get('uptime_summary') or {}).get('aggregate_status')}",
        "",
        "## Incidents",
    ]
    for inc in report.get("incidents") or []:
        if isinstance(inc, dict):
            lines.append(f"- {inc.get('name')} ({inc.get('mtime_iso')})")
    lines.extend(["", "## Publish stats", "```json", json.dumps(report.get("publish_stats"), indent=2)[:8000], "```"])
    lines.extend(["", "## Operator interventions"])
    for op in (report.get("operator_interventions") or [])[:15]:
        if isinstance(op, dict):
            lines.append(f"- {op.get('ts')} `{op.get('action')}` → {op.get('outcome')}")
    lines.extend(["", "## Editorial drift (sample)"])
    drift = (report.get("editorial_drift") or {}).get("results") or []
    for d in drift[:10]:
        if isinstance(d, dict):
            lines.append(f"- {d.get('summary')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    from app.config import load_settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("-o", "--output-dir", default="")
    args = parser.parse_args()
    settings = load_settings()
    report = build_report(settings, hours=args.hours)
    out_dir = Path(args.output_dir) if args.output_dir else Path(settings.runtime_state_dir) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    json_path = out_dir / f"ops_report_{ts}.json"
    md_path = out_dir / f"ops_report_{ts}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
