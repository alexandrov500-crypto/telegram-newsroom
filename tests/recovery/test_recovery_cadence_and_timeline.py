from __future__ import annotations

from dashboard.timeline import append_timeline_event, load_timeline_tail
from editorial.intelligence_store import cadence_state_path, load_json, save_json
from editorial.suppression_memory import record_suppression_ttl
from tests.conftest import minimal_test_settings


def test_cadence_suppression_and_timeline_survive_reload(tmp_path) -> None:
    rd = str(tmp_path / "rt")
    cad = cadence_state_path(rd)
    save_json(cad, {"version": 1, "channels": {"ch1": {"last_publish_ts": 1.0}}})
    record_suppression_ttl(rd, "k1", 600.0, reason="recovery_test")
    append_timeline_event(rd, "recovery_tick", {"n": 1})

    data = load_json(cad, {})
    assert data.get("channels", {}).get("ch1", {}).get("last_publish_ts") == 1.0
    tail = load_timeline_tail(rd, limit=5)
    assert any((e.get("kind") == "recovery_tick") for e in tail)

    s = minimal_test_settings(runtime_state_dir=rd)
    assert s.runtime_state_dir == rd
    tail2 = load_timeline_tail(s.runtime_state_dir, limit=5)
    assert len(tail2) >= 1
