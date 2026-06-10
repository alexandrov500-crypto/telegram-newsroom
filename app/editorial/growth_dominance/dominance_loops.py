"""Editorial Dominance Loops — Awareness / Retention / Authority."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

_AWARENESS = re.compile(
    r"(breaking|срочно|urgent|шок|rate\s+decision|ставк.*(?:повыш|сниз|остав)|"
    r"openai|nvidia|sanction|санкци|crash|обвал|record\s+high)",
    re.I,
)
_RETENTION = re.compile(
    r"(утр|вечер|сводк|brief|итоги|snapshot|5\s+вещ|3\s+вещ|closing|morning|wrap)",
    re.I,
)
_AUTHORITY = re.compile(
    r"(контекст|explainer|почему\s+важ|что\s+значит|meaning|implication|разбор|механизм)",
    re.I,
)


class DominanceLoop(str, Enum):
    AWARENESS = "awareness"
    RETENTION = "retention"
    AUTHORITY = "authority"


def classify_dominance_loop(
    text: str,
    *,
    post_type: str = "",
    is_breaking: bool = False,
    publishing_mode: str = "core",
    gravity: float = 0.0,
) -> DominanceLoop:
    t = text or ""
    pt = (post_type or "").lower()

    if publishing_mode == "editorial_synthesis" or pt == "digest" or _RETENTION.search(t):
        return DominanceLoop.RETENTION
    if pt in {"explainer", "context"} or _AUTHORITY.search(t) or publishing_mode == "elastic_fill":
        return DominanceLoop.AUTHORITY
    if is_breaking or pt == "breaking" or _AWARENESS.search(t) or gravity >= 80:
        return DominanceLoop.AWARENESS
    if gravity >= 60:
        return DominanceLoop.AWARENESS
    return DominanceLoop.AUTHORITY


def loop_objective(loop: DominanceLoop) -> dict[str, str]:
    return {
        DominanceLoop.AWARENESS: {
            "goal": "forwards",
            "format": "short_shareable_insight",
        },
        DominanceLoop.RETENTION: {
            "goal": "daily_return",
            "format": "structured_ritual",
        },
        DominanceLoop.AUTHORITY: {
            "goal": "trust_and_saves",
            "format": "context_and_explanation",
        },
    }[loop]


def loop_to_dict(loop: DominanceLoop) -> dict[str, Any]:
    obj = loop_objective(loop)
    return {"loop": loop.value, **obj}
