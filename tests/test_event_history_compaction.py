from __future__ import annotations

import time

from editorial.events import append_event_history, compact_event_history
from editorial.intelligence_store import event_history_path, save_json


def test_compact_event_history_age(tmp_path) -> None:
    rd = str(tmp_path)
    p = event_history_path(rd)
    save_json(
        p,
        {
            "version": 1,
            "events": [{"fingerprint": "old", "combined_text_excerpt": "x", "ts": time.time() - 1_000_000}],
        },
    )
    out = compact_event_history(rd, max_entries=50, max_age_sec=3600.0)
    assert out["kept"] == 0
    append_event_history(rd, fingerprint="a", combined_text_excerpt="hello")
    out2 = compact_event_history(rd, max_entries=1)
    assert out2["kept"] == 1
