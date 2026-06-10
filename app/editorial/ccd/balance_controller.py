"""7-day content balance controller — category weekly shares."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.ccd.config import daily_category_max_pct

_WEEKLY_TARGETS: dict[str, tuple[float, float]] = {
    "macro": (0.18, 0.22),
    "ai": (0.18, 0.22),
    "tech": (0.18, 0.22),
    "geopolitics": (0.15, 0.18),
    "markets": (0.12, 0.15),
    "business": (0.10, 0.12),
    "energy": (0.05, 0.08),
    "science": (0.05, 0.08),
    "explainer": (0.10, 0.15),
}

_CATEGORY_PATTERNS: dict[str, str] = {
    "macro": "macro",
    "ai": "ai",
    "tech": "tech",
    "geopolitics": "geopolitics",
    "markets": "markets",
    "business": "business",
    "energy": "energy",
    "science": "science",
    "explainer": "explainer",
}


@dataclass(frozen=True)
class BalanceDecision:
    category: str
    daily_pct: float
    weekly_pct: float
    within_balance: bool
    defer_category: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "daily_pct": round(self.daily_pct, 3),
            "weekly_pct": round(self.weekly_pct, 3),
            "within_balance": self.within_balance,
            "defer_category": self.defer_category,
            "reason": self.reason,
            "weekly_targets": {k: list(v) for k, v in _WEEKLY_TARGETS.items()},
        }


def infer_content_category(text: str, editorial_category: str = "") -> str:
    cat = (editorial_category or "").lower()
    if cat in _CATEGORY_PATTERNS:
        return cat
    t = (text or "").lower()
    if any(k in t for k in ("openai", "nvidia", "gpt", "нейросет")):
        return "ai"
    if any(k in t for k in ("sanction", "war", "nato", "геополит")):
        return "geopolitics"
    if any(k in t for k in ("fed", "cpi", "инфляц", "macro", "цб")):
        return "macro"
    if any(k in t for k in ("moex", "nasdaq", "рынок", "бирж")):
        return "markets"
    if any(k in t for k in ("earnings", "ipo", "компан", "business")):
        return "business"
    if any(k in t for k in ("oil", "gas", "нефт", "energy")):
        return "energy"
    if any(k in t for k in ("science", "research", "trend")):
        return "science"
    return "macro"


def evaluate_balance(
    category: str,
    *,
    runtime_dir: str | None = None,
) -> BalanceDecision:
    from app.editorial.ccd.state import load_state

    import time

    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    data = load_state(runtime_dir)
    day = dict((data.get("days") or {}).get(day_key) or {})
    week = dict(data.get("week_counts") or {})

    day_counts = dict(day.get("category_counts") or {})
    day_total = max(1, sum(int(v) for v in day_counts.values()))
    daily_pct = int(day_counts.get(category) or 0) / day_total

    week_total = max(1, sum(int(v) for v in week.values()))
    weekly_pct = int(week.get(category) or 0) / week_total

    max_daily = daily_category_max_pct()
    defer = daily_pct >= max_daily

    lo, hi = _WEEKLY_TARGETS.get(category, (0.05, 0.25))
    within = not defer and weekly_pct <= hi + 0.05

    reason = "balance_ok" if within else "category_over_cap"
    if defer:
        reason = "daily_category_cap"

    return BalanceDecision(
        category=category,
        daily_pct=daily_pct,
        weekly_pct=weekly_pct,
        within_balance=within,
        defer_category=defer,
        reason=reason,
    )
