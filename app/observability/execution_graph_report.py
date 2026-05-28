"""Offline execution-graph consistency report (DB + traces JSONL + log tail)."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.burnin_eval import scan_log_contract
from app.observability.execution_graph_classification import classify_anomaly, partition_anomalies
from app.observability.execution_graph_safety import safety_payload
from app.reliability.terminal_state_resolver import TERMINAL_STATES

_VALID_TERMINAL = TERMINAL_STATES


def _load_jsonl_traces(path: Path, *, limit: int = 500) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _db_finished_ticks(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tick_id, status, finished_at, started_at, duration_ms,
               json_extract(detail_json,'$.terminal_state') AS terminal_state
        FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
        ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "tick_id": str(r[0]),
            "status": str(r[1]),
            "finished_at": str(r[2] or ""),
            "started_at": str(r[3] or ""),
            "duration_ms": r[4],
            "terminal_state": str(r[5] or ""),
        }
        for r in rows
    ]


def _scan_log_graph_signals(log_path: Path) -> dict[str, int]:
    base = {
        "execution_graph_anomaly": 0,
        "execution_graph_finalize": 0,
        "execution_graph_summarize": 0,
        "execution_graph_publish_gate": 0,
        "pipeline_terminal_state": 0,
        "publish_audit_blocked": 0,
        "publish_audit_allowed": 0,
    }
    if not log_path.is_file():
        return base
    try:
        size = log_path.stat().st_size
        tail_bytes = 8_000_000
        with log_path.open("rb") as fh:
            if size > tail_bytes:
                fh.seek(size - tail_bytes)
                fh.readline()
            chunk = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return base
    base["execution_graph_anomaly"] = len(re.findall(r"execution_graph_anomaly_detected", chunk))
    base["execution_graph_critical"] = len(
        re.findall(r'execution_graph_anomaly_detected.*"severity":\s*"critical"', chunk)
    )
    base["execution_graph_warning"] = len(
        re.findall(r'execution_graph_anomaly_detected.*"severity":\s*"warning"', chunk)
    )
    base["safe_recovery_activated"] = len(re.findall(r"execution_graph\.safe_recovery_activated", chunk))
    base["execution_graph_finalize"] = len(re.findall(r"execution_graph\.finalize", chunk))
    base["execution_graph_summarize"] = len(re.findall(r"execution_graph\.summarize_path", chunk))
    base["execution_graph_publish_gate"] = len(re.findall(r"execution_graph\.publish_gate", chunk))
    base["pipeline_terminal_state"] = len(re.findall(r"pipeline\.terminal_state", chunk))
    base["publish_audit_blocked"] = len(
        re.findall(r'"publish_decision":\s*"blocked"', chunk)
    )
    base["publish_audit_allowed"] = len(
        re.findall(r'"publish_decision":\s*"allowed"', chunk)
    )
    return base


def build_execution_graph_report(
    *,
    db_path: Path | None,
    runtime_dir: Path,
    log_path: Path,
    window_ticks: int = 100,
) -> dict[str, Any]:
    traces_path = runtime_dir / "execution_graph_traces.jsonl"
    traces = _load_jsonl_traces(traces_path, limit=window_ticks)
    db_ticks: list[dict[str, Any]] = []
    if db_path and db_path.is_file():
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        db_ticks = _db_finished_ticks(conn, limit=window_ticks)
        conn.close()

    log_signals = _scan_log_graph_signals(log_path)

    anomalies: list[dict[str, Any]] = []
    consistent = 0
    warning_ticks = 0
    critical_ticks = 0
    metrics_eligible = 0
    for tr in traces:
        tick_anomalies = list(tr.get("anomalies") or [])
        if tr.get("summarize_calls", 0) != 1:
            tick_anomalies.append(f"summarize_calls={tr.get('summarize_calls')}")
        if tr.get("finalize_calls", 0) != 1:
            tick_anomalies.append(f"finalize_calls={tr.get('finalize_calls')}")
        if tr.get("publish_success", 0) > 0 and tr.get("publish_gate_allowed", 0) < 1:
            tick_anomalies.append("publish_without_gate_allowed")
        ts = str(tr.get("terminal_state") or "")
        if ts and ts not in _VALID_TERMINAL:
            tick_anomalies.append(f"invalid_terminal:{ts}")
        warnings, critical = partition_anomalies(tick_anomalies)
        warnings = list(tr.get("anomaly_warnings") or warnings)
        critical = list(tr.get("anomaly_critical") or critical)
        if critical:
            critical_ticks += 1
        elif warnings:
            warning_ticks += 1
        if tick_anomalies or critical or warnings:
            anomalies.append(
                {
                    "tick_id": tr.get("tick_id"),
                    "warnings": warnings,
                    "critical": critical,
                    "corrupted": bool(tr.get("corrupted")),
                }
            )
        else:
            consistent += 1
            metrics_eligible += 1

    trace_n = len(traces)
    consistency_rate = round(consistent / trace_n, 4) if trace_n else None
    critical_per_100 = round((critical_ticks / trace_n) * 100, 2) if trace_n else 0.0
    warning_per_100 = round((warning_ticks / trace_n) * 100, 2) if trace_n else 0.0
    anomalies_per_100 = round((len(anomalies) / trace_n) * 100, 2) if trace_n else 0.0
    mismatch_rate = round(1.0 - (consistent / trace_n), 4) if trace_n else None

    db_missing_terminal = sum(
        1 for t in db_ticks if str(t.get("terminal_state") or "") not in _VALID_TERMINAL
    )
    db_invalid_status = sum(
        1 for t in db_ticks if str(t.get("status") or "") not in ("ok", "reject")
    )

    mismatch_notes: list[str] = []
    if trace_n and log_signals["pipeline_terminal_state"]:
        ratio = log_signals["pipeline_terminal_state"] / max(1, trace_n)
        if ratio > 1.5 or ratio < 0.5:
            mismatch_notes.append(
                f"log_terminal_state_vs_traces_ratio={ratio:.2f}"
            )

    publish_correctness = 1.0
    if traces:
        pub_ticks = [t for t in traces if int(t.get("publish_success") or 0) > 0]
        bad_pub = [
            t
            for t in pub_ticks
            if int(t.get("publish_gate_allowed") or 0) < 1
            or "publish_without_gate_allowed" in (t.get("anomalies") or [])
        ]
        publish_correctness = round(1.0 - len(bad_pub) / max(1, len(pub_ticks)), 4) if pub_ticks else 1.0

    safety = safety_payload(str(runtime_dir))
    unresolved_critical = int(safety.get("critical_events_total") or 0)
    log_critical = int(log_signals.get("execution_graph_critical") or 0)

    ready = (
        trace_n >= 3
        and critical_ticks == 0
        and critical_per_100 == 0.0
        and db_missing_terminal == 0
        and db_invalid_status == 0
        and log_critical == 0
        and consistency_rate == 1.0
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_ticks": window_ticks,
        "trace_samples": trace_n,
        "consistency_rate": consistency_rate,
        "execution_graph_mismatch_rate": mismatch_rate,
        "anomalies_per_100_ticks": anomalies_per_100,
        "warning_anomalies_per_100_ticks": warning_per_100,
        "critical_anomalies_per_100_ticks": critical_per_100,
        "publish_correctness_rate": publish_correctness,
        "finalize_consistency_rate": consistency_rate,
        "metrics_eligible_ticks": metrics_eligible,
        "log_signals": log_signals,
        "safety": safety,
        "db_ticks_sampled": len(db_ticks),
        "db_missing_terminal": db_missing_terminal,
        "db_invalid_status": db_invalid_status,
        "mismatch_notes": mismatch_notes,
        "anomaly_details": anomalies[:50],
        "critical_tick_count": critical_ticks,
        "warning_tick_count": warning_ticks,
        "execution_graph_ready": ready,
        "verdict": "PASS" if ready else ("CONDITIONAL" if trace_n >= 1 and critical_ticks == 0 else "FAIL"),
    }


def write_execution_graph_report(
    *,
    runtime_dir: Path,
    db_path: Path | None,
    log_path: Path,
    out_path: Path | None = None,
    window_ticks: int = 100,
) -> Path:
    report = build_execution_graph_report(
        db_path=db_path,
        runtime_dir=runtime_dir,
        log_path=log_path,
        window_ticks=window_ticks,
    )
    dest = out_path or (runtime_dir / "execution_graph_report.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest
