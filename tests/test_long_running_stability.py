from __future__ import annotations

from utils.metrics import export_snapshot, inc, reset_metrics
from utils.runtime_events import append_runtime_event, get_recent_runtime_events, reset_runtime_events_for_tests


def test_metrics_and_events_remain_bounded() -> None:
    reset_metrics()
    reset_runtime_events_for_tests()
    for i in range(120):
        inc("posts_collected", 1)
        append_runtime_event("test_tick", message=f"n={i}", draft_id=i % 7)
    snap = export_snapshot()
    assert int(snap.get("counters", {}).get("posts_collected", 0)) == 120
    ev = get_recent_runtime_events(5000)
    assert len(ev) < 5000
