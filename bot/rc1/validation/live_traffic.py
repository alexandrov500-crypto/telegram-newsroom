from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LiveTrafficValidator:
    """Shadow vs public comparison, integrity and trust drift."""

    def evaluate(
        self,
        *,
        shadow_publish_ratio: float = 1.0,
        delivery_success: float = 1.0,
        duplicate_prevented: int = 0,
        ai_variance: float = 0.0,
        multilingual_ok: bool = True,
        replay_ok: bool = True,
        trust_avg: float = 0.85,
    ) -> dict[str, Any]:
        integrity = (
            delivery_success * 0.4
            + (1.0 - min(1.0, ai_variance)) * 0.2
            + (1.0 if multilingual_ok else 0.0) * 0.15
            + (1.0 if replay_ok else 0.0) * 0.15
            + min(1.0, duplicate_prevented / 10.0) * 0.1
        )
        confidence = (
            integrity * 0.5
            + trust_avg * 0.3
            + (1.0 - shadow_publish_ratio) * 0.2
        )
        return {
            "go_live_confidence": round(max(0.0, min(1.0, confidence)), 4),
            "publish_integrity": round(max(0.0, min(1.0, integrity)), 4),
            "shadow_ratio": shadow_publish_ratio,
            "trust_drift": round(1.0 - trust_avg, 4),
            "delivery_success": delivery_success,
        }
