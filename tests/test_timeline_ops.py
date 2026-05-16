from __future__ import annotations

from pathlib import Path

from dashboard.timeline import append_timeline_event, load_timeline_tail


def test_timeline_append_and_tail(tmp_path: Path) -> None:
    rd = str(tmp_path / "rt")
    Path(rd).mkdir(parents=True, exist_ok=True)
    append_timeline_event(rd, "unit_test", {"x": 1}, max_entries=50)
    tail = load_timeline_tail(rd, limit=5)
    assert tail and tail[0].get("kind") == "unit_test"
    assert tail[0].get("payload", {}).get("x") == 1
