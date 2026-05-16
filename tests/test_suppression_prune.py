from __future__ import annotations

import time

from editorial.suppression_memory import is_suppression_active, prune_expired_suppression_entries, record_suppression_ttl


def test_prune_expired_suppression_entries(tmp_path) -> None:
    rd = str(tmp_path)
    record_suppression_ttl(rd, "alive", 3600.0, reason="t")
    record_suppression_ttl(rd, "dead", 1.0, reason="t")
    time.sleep(1.2)
    out = prune_expired_suppression_entries(rd)
    assert out["removed"] >= 1
    assert is_suppression_active(rd, "alive") is True
    assert is_suppression_active(rd, "dead") is False
