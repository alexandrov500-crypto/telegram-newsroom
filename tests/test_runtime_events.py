from __future__ import annotations

import json
import threading

from utils.runtime_events import (
    append_runtime_event,
    clear_runtime_events,
    configure_runtime_event_buffer,
    get_recent_runtime_events,
    reset_runtime_events_for_tests,
)


def test_append_order_and_bound():
    reset_runtime_events_for_tests()
    configure_runtime_event_buffer(maxlen=5)
    for i in range(8):
        append_runtime_event("t", message=str(i), idx=i)
    recent = get_recent_runtime_events(10)
    assert len(recent) == 5
    assert [e["message"] for e in recent] == ["3", "4", "5", "6", "7"]
    configure_runtime_event_buffer(maxlen=256)


def test_clear_events():
    reset_runtime_events_for_tests()
    append_runtime_event("a", message="x")
    clear_runtime_events()
    assert get_recent_runtime_events(5) == []


def test_json_serializable_events():
    reset_runtime_events_for_tests()
    ev = append_runtime_event("k", message="m", extra={"a": 1}, n=2)
    json.dumps(ev)
    json.dumps(get_recent_runtime_events(3))


def test_threaded_append():
    reset_runtime_events_for_tests()
    configure_runtime_event_buffer(maxlen=200)

    def worker(start: int) -> None:
        for i in range(30):
            append_runtime_event("w", message=str(start + i))

    threads = [threading.Thread(target=worker, args=(n * 100,)) for n in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(get_recent_runtime_events(500)) == 90
    configure_runtime_event_buffer(maxlen=256)
