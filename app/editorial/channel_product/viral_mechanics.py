"""Viral mechanics — reference forwarding, screenshotability, share density."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_REFERENCE_MARKERS = re.compile(
    r"(decision|решени|инвестор|риск|ставк|implication|почему\s+важ|ментальн|сигнал)",
    re.I,
)
_NUMBER_DENSITY = re.compile(r"\d+[,.]?\d*\s*(?:%|б\.?\s*п\.?|bp|\$|₽|млрд|bn|mln|млн)")


@dataclass(frozen=True)
class ViralMechanicsResult:
    reference_forward_score: float
    screenshot_score: float
    quoteability: float
    viral_tier: str
    use_growth_brief: bool
    enable_share_nudge: bool
    enable_open_loop: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_forward_score": round(self.reference_forward_score, 2),
            "screenshot_score": round(self.screenshot_score, 2),
            "quoteability": round(self.quoteability, 2),
            "viral_tier": self.viral_tier,
            "use_growth_brief": self.use_growth_brief,
            "enable_share_nudge": self.enable_share_nudge,
            "enable_open_loop": self.enable_open_loop,
        }


def evaluate_viral_mechanics(
    text: str,
    *,
    ueos_total: float = 0.0,
    crs_total: float = 0.0,
    flagship: bool = False,
    growth_brief_min: int = 68,
) -> ViralMechanicsResult:
    t = text or ""
    words = len(t.split())

    ref = 35.0
    if _REFERENCE_MARKERS.search(t):
        ref += 25.0
    if _NUMBER_DENSITY.search(t):
        ref += 15.0
    if crs_total >= 70:
        ref += 12.0
    ref = min(100.0, ref)

    screenshot = min(100.0, 40.0 + (20 if words <= 180 else 10) + (15 if _NUMBER_DENSITY.search(t) else 0))
    quote = min(100.0, ref * 0.85 + (10 if flagship else 0))

    if flagship or ref >= 80:
        tier = "viral_flagship"
    elif ref >= 65 or ueos_total >= 78:
        tier = "reference_forward"
    elif ref >= 50:
        tier = "enhanced"
    else:
        tier = "standard"

    use_brief = flagship or ref >= growth_brief_min or ueos_total >= 75
    share = ref >= 55 or flagship
    open_loop = ueos_total >= 65 and not flagship

    return ViralMechanicsResult(
        reference_forward_score=ref,
        screenshot_score=screenshot,
        quoteability=quote,
        viral_tier=tier,
        use_growth_brief=use_brief,
        enable_share_nudge=share,
        enable_open_loop=open_loop,
    )
