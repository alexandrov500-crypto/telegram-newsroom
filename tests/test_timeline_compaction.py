from __future__ import annotations

from editorial.intelligence_store import operational_timeline_path, save_json
from dashboard.timeline import append_timeline_event, compact_operational_timeline


def test_compact_timeline_age_and_cap(tmp_path) -> None:
    import time

    rd = str(tmp_path)
    p = operational_timeline_path(rd)
    save_json(p, {"version": 1, "events": [{"ts": time.time() - 1_000_000, "kind": "old", "payload": {}}]})
    out = compact_operational_timeline(rd, max_entries=5, max_age_sec=3600.0)
    assert out["kept"] == 0
    append_timeline_event(rd, "fresh", {"x": 1}, max_entries=500)
    append_timeline_event(rd, "fresh2", {"x": 2}, max_entries=500)
    out2 = compact_operational_timeline(rd, max_entries=1)
    assert out2["kept"] == 1
