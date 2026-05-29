"""Premium intelligence layer — deep analysis gating."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass


_PREMIUM_SIGNALS = re.compile(
    r"(синтез|прогноз|forecast|outlook|сценар|implication|следств|"
    r"next\s+week|на\s+недел|early\s+signal|deep\s+dive|разбор)",
    re.I,
)


@dataclass(frozen=True)
class PremiumClassification:
    is_premium: bool
    tier: str  # standard | premium | intel
    insight_score: float
    free_preview: str
    reason: str


def _enabled() -> bool:
    return os.getenv("W5_PREMIUM_LAYER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def classify_premium_content(
    content: str,
    *,
    insight_score: float = 0.0,
    vertical: str = "general",
) -> PremiumClassification:
    if not _enabled():
        return PremiumClassification(False, "standard", insight_score, content or "", "disabled")

    t = (content or "").strip()
    min_insight = float(os.getenv("W5_PREMIUM_MIN_INSIGHT", "0.72"))
    has_signal = bool(_PREMIUM_SIGNALS.search(t))
    long_enough = len(t) >= 300

    if insight_score >= 0.82 and long_enough:
        tier = "intel"
    elif insight_score >= min_insight and (has_signal or long_enough):
        tier = "premium"
    else:
        return PremiumClassification(False, "standard", insight_score, t, "below_threshold")

    preview_len = int(os.getenv("W5_PREMIUM_FREE_PREVIEW_CHARS", "280"))
    preview = t[:preview_len].rsplit(" ", 1)[0] + "…" if len(t) > preview_len else t
    return PremiumClassification(True, tier, insight_score, preview, "ok")


def split_free_premium_body(content: str, classification: PremiumClassification) -> tuple[str, str]:
    """Return (free_channel_body, premium_channel_body)."""
    if not classification.is_premium:
        return content, ""
    free = classification.free_preview
    gate = os.getenv("W5_PREMIUM_GATE_MESSAGE", "Полный разбор — в premium-канале.").strip()
    free_body = f"{free}\n\n{gate}"
    premium_body = content
    return free_body, premium_body


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode()).hexdigest()[:20]
