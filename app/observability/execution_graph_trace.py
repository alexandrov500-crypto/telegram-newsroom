"""Runtime execution-graph tracing with WARNING/CRITICAL classification."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.observability.execution_graph_classification import (
    AnomalySeverity,
    classify_anomaly,
    partition_anomalies,
)
from app.observability.execution_graph_safety import activate_safe_recovery
from utils.operational_context import current_tick_id
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_active: dict[str, TickGraphTrace] = {}
_completed_buffer: list[dict[str, Any]] = []
_MAX_BUFFER = 200


@dataclass
class TickGraphTrace:
    tick_id: str
    started_monotonic: float
    summarize_calls: int = 0
    publish_gate_evals: int = 0
    publish_gate_allowed: int = 0
    publish_success: int = 0
    finalize_calls: int = 0
    terminal_state: str | None = None
    finalized_monotonic: float | None = None
    anomalies: list[str] = field(default_factory=list)
    anomaly_warnings: list[str] = field(default_factory=list)
    anomaly_critical: list[str] = field(default_factory=list)
    corrupted: bool = False
    metrics_excluded: bool = False


def _delayed_finalize_threshold_sec() -> float:
    raw = os.getenv("EXECUTION_GRAPH_DELAYED_FINALIZE_SEC", "").strip()
    if raw:
        try:
            return max(60.0, float(raw))
        except ValueError:
            pass
    interval_min = float(os.getenv("PIPELINE_INTERVAL_MINUTES", "15"))
    return max(300.0, interval_min * 60 * 1.5)


def _traces_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "execution_graph_traces.jsonl"


def _report_anomaly(trace: TickGraphTrace, code: str, **extra: object) -> None:
    if code not in trace.anomalies:
        trace.anomalies.append(code)
    severity = classify_anomaly(code)
    if severity == AnomalySeverity.CRITICAL:
        if code not in trace.anomaly_critical:
            trace.anomaly_critical.append(code)
    elif code not in trace.anomaly_warnings:
        trace.anomaly_warnings.append(code)

    log_event(
        logger,
        "execution_graph_anomaly_detected",
        tick_id=trace.tick_id,
        anomaly=code,
        severity=severity.value,
        **{k: v for k, v in extra.items() if v is not None},
    )

    if severity == AnomalySeverity.CRITICAL:
        trace.corrupted = True
        trace.metrics_excluded = True


def _tid() -> str | None:
    return current_tick_id()


def record_tick_begin(tick_id: str) -> None:
    now = time.monotonic()
    with _lock:
        others = [t for t in _active if t != tick_id]
        if others:
            for other in others:
                _report_anomaly(
                    _active[other],
                    "tick_overlap",
                    other_tick=tick_id,
                    active_ticks=len(_active),
                )
            t0 = _active.get(tick_id)
            if t0:
                _report_anomaly(t0, "tick_overlap", other_tick=others[0])
        _active[tick_id] = TickGraphTrace(tick_id=tick_id, started_monotonic=now)
    log_event(logger, "execution_graph.tick_begin", tick_id=tick_id)


def record_summarize_path(*, tick_id: str | None = None, ai_status: str = "") -> None:
    tid = tick_id or _tid()
    if not tid:
        return
    with _lock:
        trace = _active.get(tid)
        if trace is None:
            return
        trace.summarize_calls += 1
        if trace.summarize_calls > 1:
            _report_anomaly(trace, "duplicate_summarize_path", count=trace.summarize_calls)
    log_event(logger, "execution_graph.summarize_path", tick_id=tid, ai_status=ai_status[:64])


def record_publish_gate(*, allowed: bool, tick_id: str | None = None, layer: str = "") -> None:
    tid = tick_id or _tid()
    if not tid:
        _report_anomaly_standalone("ghost_publish_gate_no_tick", allowed=allowed, layer=layer)
        return
    with _lock:
        trace = _active.get(tid)
        if trace is None:
            _report_anomaly_standalone(
                "publish_gate_outside_active_tick",
                tick_id=tid,
                allowed=allowed,
            )
            return
        if trace.finalize_calls > 0:
            _report_anomaly(trace, "publish_gate_after_finalize", allowed=allowed)
        trace.publish_gate_evals += 1
        if allowed:
            trace.publish_gate_allowed += 1
        if trace.publish_gate_evals > 1:
            _report_anomaly(trace, "duplicate_publish_gate", count=trace.publish_gate_evals)
    log_event(
        logger,
        "execution_graph.publish_gate",
        tick_id=tid,
        allowed=allowed,
        layer=layer,
    )


def _report_anomaly_standalone(code: str, **extra: object) -> None:
    severity = classify_anomaly(code)
    log_event(
        logger,
        "execution_graph_anomaly_detected",
        anomaly=code,
        severity=severity.value,
        **{k: v for k, v in extra.items() if v is not None},
    )


def record_publish_success(*, tick_id: str | None = None, draft_id: int | None = None) -> None:
    tid = tick_id or _tid()
    if not tid:
        _report_anomaly_standalone("ghost_publish_no_tick", draft_id=draft_id)
        return
    with _lock:
        trace = _active.get(tid)
        if trace is None:
            _report_anomaly_standalone(
                "ghost_publish_outside_active_tick",
                tick_id=tid,
                draft_id=draft_id,
            )
            return
        if trace.finalize_calls > 0:
            _report_anomaly(trace, "late_publish_after_finalize", draft_id=draft_id)
        if trace.publish_gate_allowed < 1:
            _report_anomaly(trace, "publish_without_gate_allowed", draft_id=draft_id)
        trace.publish_success += 1
    log_event(logger, "execution_graph.publish_success", tick_id=tid, draft_id=draft_id)


def record_finalize_begin(*, tick_id: str | None = None) -> None:
    tid = tick_id or _tid()
    if not tid:
        return
    with _lock:
        trace = _active.get(tid)
        if trace is None:
            return
        if trace.finalize_calls >= 1:
            _report_anomaly(trace, "finalize_race_duplicate_attempt", count=trace.finalize_calls + 1)
        elapsed = time.monotonic() - trace.started_monotonic
        if elapsed > _delayed_finalize_threshold_sec():
            _report_anomaly(
                trace,
                "delayed_finalize",
                elapsed_sec=round(elapsed, 1),
                threshold_sec=_delayed_finalize_threshold_sec(),
            )
        if trace.summarize_calls < 1:
            _report_anomaly(trace, "missing_summarize_path")
        trace.finalize_calls += 1


def complete_execution_graph_trace(
    *,
    terminal_state: str,
    tick_id: str | None = None,
    runtime_dir: str | None = None,
) -> dict[str, Any]:
    """
    Close tick trace, classify anomalies, activate safe recovery on CRITICAL.
    Returns metadata merged into pipeline_ticks.detail_json.
    """
    tid = tick_id or _tid()
    if not tid:
        return {}
    rd = runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")

    with _lock:
        trace = _active.pop(tid, None)
        if trace is None:
            _report_anomaly_standalone(
                "missing_finalize_begin",
                tick_id=tid,
                terminal_state=terminal_state,
            )
            activate_safe_recovery(
                rd,
                tick_id=tid,
                critical_codes=["missing_finalize_begin"],
                terminal_state=terminal_state,
            )
            return {
                "corrupted": True,
                "metrics_excluded": True,
                "anomaly_critical": ["missing_finalize_begin"],
                "anomaly_warnings": [],
                "terminal_state": terminal_state,
            }

        trace.terminal_state = terminal_state
        trace.finalized_monotonic = time.monotonic()

        if trace.finalize_calls != 1:
            _report_anomaly(trace, "duplicate_finalize", count=trace.finalize_calls)
        if trace.summarize_calls != 1:
            _report_anomaly(trace, f"summarize_calls={trace.summarize_calls}")
        if trace.publish_gate_evals != 1 and trace.publish_success > 0:
            _report_anomaly(trace, f"publish_gate_evals={trace.publish_gate_evals}")
        if trace.publish_success > 0 and trace.publish_gate_allowed < 1:
            _report_anomaly(trace, "publish_consistency_violation")

        warnings, critical = partition_anomalies(trace.anomalies)
        trace.anomaly_warnings = warnings
        trace.anomaly_critical = critical
        if critical:
            trace.corrupted = True
            trace.metrics_excluded = True

        payload = asdict(trace)
        _completed_buffer.append(payload)
        if len(_completed_buffer) > _MAX_BUFFER:
            del _completed_buffer[: len(_completed_buffer) - _MAX_BUFFER]

    if trace.anomaly_critical:
        activate_safe_recovery(
            rd,
            tick_id=tid,
            critical_codes=trace.anomaly_critical,
            terminal_state=terminal_state,
        )

    log_event(
        logger,
        "execution_graph.finalize",
        tick_id=tid,
        terminal_state=terminal_state,
        warning_count=len(trace.anomaly_warnings),
        critical_count=len(trace.anomaly_critical),
        corrupted=trace.corrupted,
    )

    try:
        path = _traces_path(rd)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        log_event(logger, "execution_graph.trace_persist_failed", error=repr(exc)[:120])

    return {
        "corrupted": trace.corrupted,
        "metrics_excluded": trace.metrics_excluded,
        "anomaly_warnings": trace.anomaly_warnings,
        "anomaly_critical": trace.anomaly_critical,
        "summarize_calls": trace.summarize_calls,
        "publish_gate_evals": trace.publish_gate_evals,
        "finalize_calls": trace.finalize_calls,
        "publish_success": trace.publish_success,
        "terminal_state": terminal_state,
    }


def record_finalize_complete(
    *,
    terminal_state: str,
    tick_id: str | None = None,
    runtime_dir: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias — prefer complete_execution_graph_trace from finalizer."""
    return complete_execution_graph_trace(
        terminal_state=terminal_state,
        tick_id=tick_id,
        runtime_dir=runtime_dir,
    )


def active_tick_count() -> int:
    with _lock:
        return len(_active)


def flush_active_traces_on_shutdown(runtime_dir: str | None) -> int:
    """Persist in-flight graph traces when the process exits without finalize."""
    if not runtime_dir:
        return 0
    with _lock:
        if not _active:
            return 0
        pending = list(_active.items())
        _active.clear()
    path = _traces_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with path.open("a", encoding="utf-8") as fh:
            for _tid, trace in pending:
                _report_anomaly(trace, "shutdown_abandoned")
                payload = asdict(trace)
                payload["terminal_state"] = "shutdown_abandoned"
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                written += 1
    except OSError as exc:
        log_event(logger, "execution_graph.shutdown_flush_failed", error=repr(exc)[:120])
        return 0
    if written:
        log_event(logger, "execution_graph.shutdown_flush", count=written, path=str(path))
    return written


def recent_completed_traces(*, limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        return list(_completed_buffer[-limit:])
