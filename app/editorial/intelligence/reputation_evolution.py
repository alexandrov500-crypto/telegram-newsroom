"""Source reputation evolution hints (wraps source_reputation.json)."""

from __future__ import annotations

from typing import Any


def source_usefulness_snapshot(runtime_dir: str, channels: list[str]) -> dict[str, Any]:
    from utils.source_reputation import export_channel_scores_for_priority

    scores = export_channel_scores_for_priority(runtime_dir)
    out: dict[str, Any] = {}
    for ch in channels:
        key = str(ch or "").strip().lower()
        row = scores.get(key) or {}
        pub = int(row.get("publishes") or 0)
        dup = int(row.get("duplicate_signals") or 0)
        rej = int(row.get("rejects") or 0)
        usefulness = float(row.get("score") or 0.5)
        rumor_tendency = min(1.0, dup / max(1, pub))
        signal_noise = round(usefulness * (1.0 - 0.3 * rumor_tendency), 4)
        out[key] = {
            "usefulness": usefulness,
            "signal_noise": signal_noise,
            "rumor_tendency": round(rumor_tendency, 4),
            "publishes": pub,
            "rejects": rej,
        }
    return out
