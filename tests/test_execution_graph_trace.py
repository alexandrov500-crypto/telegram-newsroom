"""Execution graph trace invariants."""

from __future__ import annotations

from utils.operational_context import begin_pipeline_tick, reset_tick_id

from app.observability import execution_graph_trace as eg


def test_single_finalize_path(tmp_path):
    eg._active.clear()
    eg._completed_buffer.clear()
    rd = str(tmp_path)
    tid, tok, _ = begin_pipeline_tick()
    try:
        eg.record_tick_begin(tid)
        eg.record_summarize_path(tick_id=tid)
        eg.record_publish_gate(allowed=True, tick_id=tid, layer="ok")
        eg.record_finalize_begin(tick_id=tid)
        eg.record_finalize_complete(terminal_state="committed_idle", tick_id=tid, runtime_dir=rd)
    finally:
        reset_tick_id(tok)
    assert len(eg._active) == 0
    assert eg._completed_buffer[-1]["finalize_calls"] == 1
    assert eg._completed_buffer[-1]["summarize_calls"] == 1


def test_duplicate_finalize_anomaly(tmp_path):
    eg._active.clear()
    rd = str(tmp_path)
    tid, tok, _ = begin_pipeline_tick()
    try:
        eg.record_tick_begin(tid)
        eg.record_summarize_path(tick_id=tid)
        eg.record_finalize_begin(tick_id=tid)
        eg.record_finalize_begin(tick_id=tid)
        eg.record_finalize_complete(terminal_state="committed_reject", tick_id=tid, runtime_dir=rd)
    finally:
        reset_tick_id(tok)
    last = eg._completed_buffer[-1]
    assert "finalize_race_duplicate_attempt" in last["anomalies"]
    assert last.get("corrupted") is True
    assert len(last.get("anomaly_critical") or []) >= 1
