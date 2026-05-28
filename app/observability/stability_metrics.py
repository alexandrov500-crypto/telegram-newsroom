"""Low-variance stability metrics for burn-in (read-only)."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.observability.burnin_eval import publishability_metrics, scan_log_contract


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / len(values)


def _cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 0.0
    return math.sqrt(_variance(values)) / mean


def _reject_reason_stability(conn: sqlite3.Connection, *, limit: int = 40) -> float:
    """1.0 = single dominant reason; lower = more churn across reasons."""
    rows = conn.execute(
        """
        SELECT json_extract(detail_json,'$.terminal_reason')
        FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
          AND json_extract(detail_json,'$.terminal_state')='committed_reject'
        ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    if not rows:
        return 1.0
    counts: dict[str, int] = {}
    for (reason,) in rows:
        key = str(reason or "unknown")[:48]
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values())
    top = max(counts.values())
    return round(top / total, 3)


def _publish_cadence_hours(conn: sqlite3.Connection, *, limit: int = 20) -> list[float]:
    """Hours between consecutive published drafts (if published_at available)."""
    try:
        rows = conn.execute(
            """
            SELECT published_at FROM drafts
            WHERE status='published' AND published_at IS NOT NULL
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    times: list[datetime] = []
    for (raw,) in rows:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            times.append(dt)
        except (ValueError, TypeError):
            continue
    if len(times) < 2:
        return []
    times.sort()
    gaps: list[float] = []
    for i in range(1, len(times)):
        gaps.append((times[i] - times[i - 1]).total_seconds() / 3600.0)
    return gaps


def _finished_terminal_tick_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
          AND status IN ('ok', 'reject')
          AND json_extract(detail_json,'$.terminal_state') IN (
            'committed_draft','committed_reject','committed_idle'
          )
          AND COALESCE(json_extract(detail_json,'$.execution_graph.metrics_excluded'), 0) = 0
        """
    ).fetchone()
    return int(row[0] if row else 0)


def compute_system_stability_score(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Score 0–100 (higher = more stable). Uses **finished ticks only** (ok/reject + valid terminal).
    """
    pub = publishability_metrics(conn)
    durations: list[float] = []
    for (dur,) in conn.execute(
        """
        SELECT duration_ms FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
          AND status IN ('ok', 'reject')
          AND duration_ms IS NOT NULL
          AND json_extract(detail_json,'$.terminal_state') IN (
            'committed_draft','committed_reject','committed_idle'
          )
          AND COALESCE(json_extract(detail_json,'$.execution_graph.metrics_excluded'), 0) = 0
          AND COALESCE(json_extract(detail_json,'$.execution_graph.corrupted'), 0) = 0
        ORDER BY id DESC LIMIT 30
        """
    ).fetchall():
        if dur is not None:
            durations.append(float(dur) / 1000.0)

    tick_cv = _cv(durations)
    cadence = _publish_cadence_hours(conn)
    cadence_cv = _cv(cadence) if cadence else 0.0
    reject_stability = _reject_reason_stability(conn)

    running = int(pub.get("running_ticks") or 0)
    finished_terminal = _finished_terminal_tick_count(conn)

    score = 100.0
    score -= min(40.0, running * 15.0)
    score -= min(25.0, tick_cv * 30.0)
    score -= min(20.0, cadence_cv * 25.0)
    score -= min(15.0, (1.0 - reject_stability) * 30.0)
    if finished_terminal < 3:
        score -= 10.0
    score = max(0.0, min(100.0, round(score, 1)))

    return {
        "system_stability_score": score,
        "tick_duration_cv": round(tick_cv, 3),
        "publish_cadence_cv": round(cadence_cv, 3),
        "reject_reason_stability": reject_stability,
        "running_ticks": running,
        "finished_terminal_ticks": finished_terminal,
        "sample_finished_ticks": len(durations),
        "publishability": pub,
    }


def evaluate_burnin_stability(conn: sqlite3.Connection, *, min_score: float = 60.0) -> tuple[str, list[str]]:
    metrics = compute_system_stability_score(conn)
    reasons: list[str] = []
    score = float(metrics["system_stability_score"])
    if score < min_score:
        reasons.append(f"stability_score_low:{score}<{min_score}")
    if int(metrics.get("running_ticks") or 0) > 0:
        reasons.append(f"running_ticks:{metrics['running_ticks']}")
    if float(metrics.get("tick_duration_cv") or 0) > 0.85:
        reasons.append(f"tick_duration_unstable:cv={metrics['tick_duration_cv']}")
    if not reasons:
        return "PASS", []
    if score >= min_score * 0.75 and not any("running_ticks" in r for r in reasons):
        return "CONDITIONAL", reasons
    return "FAIL", reasons


def build_stability_report(
    conn: sqlite3.Connection,
    *,
    log_path: str | None = None,
    runtime_dir: str | None = None,
) -> dict[str, Any]:
    import os
    from pathlib import Path

    from app.observability.runtime_resilience_report import build_runtime_resilience_section

    metrics = compute_system_stability_score(conn)
    verdict, reasons = evaluate_burnin_stability(conn)
    log_scan = scan_log_contract(Path(log_path) if log_path else Path("logs/local-run.log"))
    rd = Path(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    resilience = build_runtime_resilience_section(rd)
    continuity: dict[str, Any] = {}
    try:
        from app.observability.publish_continuity import compute_autonomous_continuity_score

        continuity = compute_autonomous_continuity_score(conn, runtime_dir=str(rd))
    except Exception:
        pass
    protection_history = {
        "activation_count": resilience.get("protection_activation_count"),
        "recovery_count": resilience.get("recovery_count"),
        "recovery_loops": resilience.get("recovery_loops"),
    }
    return {
        "verdict": verdict,
        "reasons": reasons,
        "metrics": metrics,
        "runtime_resilience": resilience,
        "publish_continuity": continuity,
        "uptime_health_score": resilience.get("uptime_health_score"),
        "protection_history": protection_history,
        "log_contract": log_scan,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
