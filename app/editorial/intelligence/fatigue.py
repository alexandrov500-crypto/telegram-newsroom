"""Topic fatigue — advisory score 0..1 (higher = more fatigued)."""

from __future__ import annotations

import os
import re
from typing import Any

from app.editorial.intelligence.memory import count_topic_in_window, hours_since_topic, topic_key_from_text

_CRYPTO_ETF = re.compile(r"(etf|биткоин|bitcoin|btc\b|crypto|крипт)", re.I)
_MACRO = re.compile(r"(fed|цб|cpi|inflation|ставк|gdp|ввп)", re.I)


def compute_topic_fatigue(
    runtime_dir: str,
    *,
    text: str,
    topic_key: str | None = None,
) -> dict[str, Any]:
    key = topic_key or topic_key_from_text(text)
    count_24h = count_topic_in_window(runtime_dir, key, hours=24.0)
    count_6h = count_topic_in_window(runtime_dir, key, hours=6.0)
    since_h = hours_since_topic(runtime_dir, key)

    score = 0.0
    reasons: list[str] = []

    if count_24h >= 5:
        score = max(score, 0.92)
        reasons.append("topic_repeat_5_in_24h")
    elif count_24h >= 3:
        score = max(score, 0.75)
        reasons.append("topic_repeat_3_in_24h")
    elif count_6h >= 2:
        score = max(score, 0.65)
        reasons.append("topic_repeat_2_in_6h")

    if since_h is not None and since_h < 2.0 and count_6h >= 1:
        score = max(score, 0.7)
        reasons.append("same_topic_within_2h")

    t = text or ""
    if _CRYPTO_ETF.search(t) and count_24h >= 2:
        score = max(score, 0.8)
        reasons.append("crypto_etf_fatigue")
    if _MACRO.search(t) and count_6h >= 2:
        score = max(score, 0.55)
        reasons.append("macro_noise_fatigue")

    return {
        "topic_key": key,
        "fatigue_score": round(min(1.0, score), 4),
        "count_24h": count_24h,
        "count_6h": count_6h,
        "hours_since_last": round(since_h, 2) if since_h is not None else None,
        "reasons": reasons,
    }


def fatigue_suppress_threshold() -> float:
    raw = os.getenv("EDITORIAL_FATIGUE_SUPPRESS_THRESHOLD", "0.92").strip()
    try:
        return max(0.5, min(float(raw), 1.0))
    except ValueError:
        return 0.92


def fatigue_enabled() -> bool:
    return os.getenv("EDITORIAL_FATIGUE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
