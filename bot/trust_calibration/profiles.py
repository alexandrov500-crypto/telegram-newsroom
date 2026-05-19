from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def operator_trust_profile(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Which subsystems operators follow vs ignore."""
    ignored_by_sub: Counter[str] = Counter()
    followed_by_sub: Counter[str] = Counter()
    overrides = 0

    for ev in events:
        sub = str(ev.get("subsystem") or "")
        action = str(ev.get("operator_action") or "")
        if action == "ignored":
            ignored_by_sub[sub] += 1
        elif action in ("confirmed", "followed", "agreement"):
            followed_by_sub[sub] += 1
        elif action == "override":
            overrides += 1

    reliance: list[tuple[str, float]] = []
    for sub in set(ignored_by_sub) | set(followed_by_sub):
        total = ignored_by_sub[sub] + followed_by_sub[sub]
        if total:
            reliance.append((sub, round(followed_by_sub[sub] / total, 3)))
    reliance.sort(key=lambda x: -x[1])

    return {
        "override_count": overrides,
        "most_ignored": ignored_by_sub.most_common(5),
        "most_followed": followed_by_sub.most_common(5),
        "reliance_ranking": reliance[:7],
    }
